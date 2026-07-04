"""The one execution loop — now an adaptive reasoning cycle.

Every iteration asks the reasoning engine for one typed Decision:
continue, observe, escalate perception, verify, replan, recover, finish
or abort. The runtime executes decisions; it never overrides them. What
used to be hardcoded control flow is now data on the event stream —
every choice carries the factors that produced it and is replayable.

Perception flows exclusively through the world model; step outcomes and
world snapshots feed beliefs; failures spawn multiple hypotheses that
recovery resolves against measured outcomes. Every branch is budgeted;
every transition emits a canonical event. LLM calls stay at the plan /
diagnose / judge boundaries — the reasoning cycle itself is deterministic.
"""
from __future__ import annotations

import time
from collections import deque
from typing import TYPE_CHECKING, Optional

from .contracts import (
    ActionOutcome,
    ActionType,
    Artifact,
    DecisionType,
    ExecutionState,
    PlannerOutput,
    Step,
    StepResult,
    StepStatus,
    Task,
    TaskContext,
    TaskResult,
    TaskStatus,
    UIElement,
    WorldState,
    utc_now_iso,
)
from .events import EventType
from .reasoning import ReasoningState

if TYPE_CHECKING:
    from .session import AgentSession

_PLACEHOLDER_LITERALS = {"{{extract}}", "{extract}", "$extract", "extracted_text"}


class ExecutionEngine:
    def __init__(self, session: "AgentSession"):
        self._s = session
        self._config = session.config
        self._last_world: Optional[WorldState] = None
        self._baseline_world: Optional[WorldState] = None
        self._exec_state: Optional[ExecutionState] = None

    # -------------------------------------------------------- world model

    def _perceive(self, task: Task, mode: str = "fast",
                  force_refresh: bool = True) -> WorldState:
        """Take a world snapshot and emit it on the canonical stream."""
        world = self._s.world.snapshot(mode=mode, force_refresh=force_refresh)
        self._last_world = world
        if self._baseline_world is None:
            self._baseline_world = world
        self._emit_world(task, world)
        return world

    def _emit_world(self, task: Task, world: WorldState) -> None:
        diff = self._s.world.last_diff
        # Inspector sample: the most useful elements, kept small on purpose —
        # the event stream is observability, not a bulk data channel.
        sample = world.interactive_elements or world.elements
        self._s.emit(
            EventType.WORLD_SNAPSHOT, task,
            mode=world.mode,
            focused_window=world.focused_window,
            windows=len(world.windows),
            elements=len(world.elements),
            interactive=len(world.interactive_elements),
            confidence=world.confidence,
            providers=[
                {"name": r.name, "source": r.source, "ok": r.ok,
                 "observations": r.observations, "latency_ms": r.latency_ms}
                for r in world.providers
            ],
            top_elements=[
                {"name": el.name, "role": el.role,
                 "confidence": el.confidence, "sources": el.sources}
                for el in sample[:12] if el.name
            ],
            changed=bool(diff.changed) if diff else False,
            summary=diff.summary if diff else "",
        )

    # ------------------------------------------------------------------ run

    def run(self, task: Task) -> TaskResult:
        start = time.time()
        context = TaskContext(instruction=task.instruction)
        state = ExecutionState()
        self._exec_state = state
        executed: list[StepResult] = []
        errors: list[str] = []

        self._s.emit(EventType.TASK_STARTED, task, instruction=task.instruction)

        self._understand_goal(task, context)
        reasoning = self._s.reasoning
        rstate = reasoning.begin(
            context.goal, context,
            emit=lambda type_, **payload: self._s.emit(type_, task, **payload),
            started_at=start,
        )

        try:
            output = self._plan(task, context, executed, state, rstate, source="planner")
            initial = output.steps if output.ok else []
            reasoning.record_plan(rstate, initial,
                                  planner_said_done=output.ok and not output.steps)
        except Exception as e:
            return self._finish(task, context, state, executed, rstate,
                                errors=[f"Planning failed: {e}"], started=start)

        if not initial and not rstate.goal_achieved_signal:
            return self._finish(task, context, state, executed, rstate,
                                errors=["Could not plan task"], started=start)

        if initial:
            self._s.emit(
                EventType.PLAN_CREATED, task,
                steps=[{"description": s.description, "action": s.action.value} for s in initial],
            )

        queue = deque(initial)
        while rstate.cycle < self._config.max_cycles:
            decision = reasoning.decide(
                rstate, queue_len=len(queue), execution=state, context=context,
                executed=executed, llm_calls=int(getattr(self._s.llm, "calls", 0) or 0),
            )

            if decision.type == DecisionType.FINISH:
                break

            if decision.type in (DecisionType.ABORT, DecisionType.NEED_USER):
                errors.append(decision.reason)
                break

            if decision.type == DecisionType.OBSERVE:
                world = self._perceive(task)
                reasoning.observe(rstate, world, self._s.world.last_diff)
                continue

            if decision.type == DecisionType.ESCALATE_PERCEPTION:
                state.vision_escalations += 1
                try:
                    world = self._perceive(task, mode="full")
                except Exception:
                    world = self._perceive(task)
                reasoning.observe(rstate, world, self._s.world.last_diff)
                continue

            if decision.type == DecisionType.VERIFY:
                world = self._perceive(task)
                reasoning.verified(rstate, world, self._s.world.last_diff)
                continue

            if decision.type == DecisionType.RECOVER and rstate.failure is not None:
                failed = rstate.failure
                if self._recover(task, failed, context, state, rstate, executed):
                    failed.status = StepStatus.HEALED
                    reasoning.failure_resolved(rstate)
                # Unrecovered: the failure stays pending; the next decision
                # escalates to a replan from the live screen.
                continue

            if decision.type == DecisionType.REPLAN:
                replanned = self._replan(task, context, executed, state, rstate,
                                         reason=decision.reason)
                if replanned:
                    if rstate.failure is not None:
                        # A replan supersedes the failed step: the goal is
                        # now pursued along a different path, and the final
                        # status belongs to verification, not to the detour.
                        rstate.failure.status = StepStatus.SKIPPED
                        self._s.emit(EventType.LOG, task,
                                     message=f"Step {rstate.failure.index} superseded by replan")
                        reasoning.failure_resolved(rstate)
                    queue = deque(replanned)
                elif rstate.failure is not None:
                    errors.append(
                        f"Step {rstate.failure.index} failed and could not be healed: "
                        f"{rstate.failure.error}"
                    )
                    break
                # An empty replan marks the planner exhausted; the next
                # decision finishes explicitly instead of a silent break.
                continue

            if decision.type == DecisionType.CONTINUE:
                if not queue:  # defensive; the decision engine finishes empty queues
                    break
                step = queue.popleft()
                result = self._run_step(task, step, context, state, executed)
                reasoning.after_step(rstate, result, context)
                self._remember_interface(state)

                if result.ok and step.action in (ActionType.OPEN_APP, ActionType.NAVIGATE_URL):
                    settle = float(step.params.get("wait", self._config.settle_after_launch_s))
                    self._s.emit(EventType.LOG, task,
                                 message=f"Waiting {settle}s for screen to settle...")
                    time.sleep(settle)

                time.sleep(self._config.settle_after_step_s)
                continue

            # Unknown decision type: stop honestly rather than guess.
            errors.append(f"Unsupported decision: {decision.type.value}")
            break

        state.cycles = rstate.cycle
        return self._finish(task, context, state, executed, rstate, errors=errors, started=start)

    # ------------------------------------------------------- understanding

    def _understand_goal(self, task: Task, context: TaskContext) -> None:
        """Analyze the goal and seed working memory with recalled knowledge.
        Failure degrades to a minimal goal; execution is never blocked."""
        try:
            goal = self._s.goals.analyze(task.instruction)
        except Exception:
            from .contracts import GoalSpec
            goal = GoalSpec(intent=task.instruction, objectives=[task.instruction])
        context.goal = goal

        try:
            recalled = self._s.memory.recall_knowledge(goal.entities + goal.required_info)
            for row in recalled:
                key = f"{row['entity']} ({row['attribute']})"
                if key not in context.facts:
                    context.facts[key] = str(row["value"])
                    context.add_note(f"recalled from memory: {key} = {row['value']}")
        except Exception:
            pass

        self._s.emit(
            EventType.GOAL_ANALYZED, task,
            intent=goal.intent, deliverable=goal.deliverable, output_format=goal.output_format,
            entities=goal.entities, objectives=goal.objectives,
            completion_criteria=goal.completion_criteria,
            recalled_facts=len(context.notes),
        )

    # ------------------------------------------------------------ planning

    def _plan(self, task: Task, context: TaskContext, executed: list[StepResult],
              state: ExecutionState, rstate: ReasoningState, source: str) -> PlannerOutput:
        world = self._perceive(task)
        self._s.reasoning.observe(rstate, world, self._s.world.last_diff, counted=False)
        world_view = self._s.world.describe(world)
        world_view = self._append_known_controls(world_view, state)
        windows = [w.title for w in world.windows]
        if not windows:
            try:
                windows = self._s.windows.list_windows()
            except Exception:
                windows = []
        return self._s.planner.plan(
            task.instruction, world_view, executed, windows,
            source=source, goal=context.goal, known_facts=context.facts,
            strategy=rstate.strategy,
        )

    def _append_known_controls(self, world_view: str, state: ExecutionState) -> str:
        """Perception memory: controls this app exposed in previous runs.
        Informs planning only — a remembered control is never clicked
        unless the live world model confirms it."""
        app = state.current_app or state.current_window
        if not app:
            return world_view
        try:
            known = self._s.memory.recall_interface(app)
        except Exception:
            known = []
        if not known:
            return world_view
        names = ", ".join(k["text"] for k in known[:12])
        return world_view + f"\nControls seen before in {app} (memory): {names}"

    def _replan(self, task: Task, context: TaskContext, executed: list[StepResult],
                state: ExecutionState, rstate: ReasoningState,
                reason: str) -> Optional[list[Step]]:
        if state.replans >= self._config.max_replans:
            self._s.emit(EventType.LOG, task, message="Replan budget exhausted")
            self._s.reasoning.record_plan(rstate, [], planner_said_done=False)
            return None
        state.replans += 1
        try:
            output = self._plan(task, context, executed, state, rstate, source="replan")
        except Exception as e:
            self._s.emit(EventType.LOG, task, message=f"Replanning failed: {e}")
            self._s.reasoning.record_plan(rstate, [], planner_said_done=False)
            return None

        if output.ok and not output.steps:
            # Deliberate planner signal: the goal is already achieved.
            self._s.reasoning.record_plan(rstate, [], planner_said_done=True)
            self._s.emit(EventType.LOG, task, message="Planner confirmed the goal is achieved")
            return None

        steps = output.steps if output.ok else []
        self._s.reasoning.record_plan(rstate, steps, planner_said_done=False)
        if steps:
            self._s.emit(EventType.REPLANNED, task, count=len(steps), reason=reason)
            return steps
        return None

    # ------------------------------------------------------------ stepping

    def _run_step(self, task: Task, step: Step, context: TaskContext,
                  state: ExecutionState, executed: list[StepResult]) -> StepResult:
        state.steps_executed += 1
        index = state.steps_executed
        self._s.emit(
            EventType.STEP_STARTED, task,
            step_number=index, description=step.description,
            action=step.action.value, source=step.source,
        )

        started_at = utc_now_iso()
        t0 = time.time()
        verdict = self._s.constraints.check_step(step, self._last_world)
        if not verdict.allowed:
            outcome = ActionOutcome(
                ok=False,
                error=f"constraint {verdict.constraint}: {verdict.reason}",
            )
        else:
            try:
                outcome = self._dispatch(task, step, context, state)
            except Exception as e:
                outcome = ActionOutcome(ok=False, error=str(e))

        result = StepResult(
            step=step,
            status=StepStatus.COMPLETED if outcome.ok else StepStatus.FAILED,
            index=index,
            started_at=started_at,
            duration_s=round(time.time() - t0, 2),
            error=outcome.error,
            data=outcome.data,
        )
        executed.append(result)
        self._s.emit(
            EventType.STEP_COMPLETED, task,
            step_number=index, description=step.description, action=step.action.value,
            status=result.status.value, duration_s=result.duration_s,
            error=result.error, data=result.data, source=step.source,
        )
        if step.action == ActionType.READ_SCREEN and result.data.get("evidence_count"):
            self._s.emit(
                EventType.EVIDENCE_COLLECTED, task,
                count=result.data["evidence_count"],
                labels=result.data.get("evidence_labels", []),
            )
        return result

    def _dispatch(self, task: Task, step: Step, context: TaskContext,
                  state: ExecutionState) -> ActionOutcome:
        action, params = step.action, step.params

        if action == ActionType.OPEN_APP:
            app = str(params.get("app", "")).strip()
            if not app:
                return ActionOutcome(ok=False, error="open_app step missing 'app'")
            outcome = self._s.apps.open(app)
            if outcome.ok:
                state.current_app = app
                state.current_window = app
                context.add_source(app)
                self._s.windows.focus(app)  # best effort
            return outcome

        if action == ActionType.NAVIGATE_URL:
            url = str(params.get("url", "")).strip()
            if not url:
                return ActionOutcome(ok=False, error="navigate_url step missing 'url'")
            outcome = self._s.apps.navigate(url)
            if outcome.ok:
                state.browser_opened = True
                context.add_source(url)
                browser = str(outcome.data.get("browser", ""))
                if browser and browser != "default":
                    state.current_app = browser
                    state.current_window = browser
                    self._s.windows.focus(browser)
            return outcome

        if action == ActionType.FOCUS_WINDOW:
            target = str(params.get("window") or params.get("app") or "").strip()
            if not target:
                return ActionOutcome(ok=False, error="focus_window step missing 'window'")
            outcome = self._s.windows.focus(target)
            if outcome.ok:
                state.current_window = target
            return outcome

        if action == ActionType.CLICK:
            query = str(params.get("find", "")).strip()
            if not query:
                return ActionOutcome(ok=False, error="click step missing 'find'")
            self._ensure_focus(step, state)
            element = self._find_with_retry(query)
            if element is None:
                # Deliberate: no blind fallback clicks. Honest failure feeds
                # recovery and replanning; a wrong click can cause real damage.
                return ActionOutcome(ok=False, error=f"Element '{query}' not found on screen")
            x, y = element.center
            outcome = self._s.actions.click(x, y)
            if outcome.ok:
                # Uncertainty propagates: consumers see what was clicked,
                # how sure perception was, and which sources agreed.
                outcome.data.update(
                    element=element.name, role=element.role,
                    confidence=element.confidence, sources=element.sources,
                )
                self._remember_element(state, element)
            return outcome

        if action in (ActionType.TYPE, ActionType.CLEAR_TYPE):
            text = self._resolve_placeholder(str(params.get("text", "")), context)
            if not text:
                return ActionOutcome(ok=False, error="type step has no text")
            self._ensure_focus(step, state)
            time.sleep(self._config.settle_before_input_s)
            if action == ActionType.CLEAR_TYPE:
                return self._s.actions.clear_and_type(text)
            return self._s.actions.type_text(text)

        if action == ActionType.PRESS:
            key = str(params.get("key", "")).strip()
            if not key:
                return ActionOutcome(ok=False, error="press step missing 'key'")
            self._ensure_focus(step, state)
            return self._s.actions.press(key)

        if action == ActionType.WAIT:
            try:
                seconds = float(params.get("wait", 1.0))
            except (TypeError, ValueError):
                seconds = 1.0
            time.sleep(seconds)
            return ActionOutcome(ok=True, data={"waited_s": seconds})

        if action == ActionType.SCROLL:
            width, height = self._s.actions.screen_size()
            direction = str(params.get("direction", "down"))
            return self._s.actions.scroll(width // 2, height // 2, direction)

        if action == ActionType.READ_SCREEN:
            time.sleep(1.0)
            world = self._perceive(task)
            goal_info = str(params.get("find") or context.instruction)
            source = context.sources[-1] if context.sources else (state.current_window or "screen")
            items = self._s.evidence.collect(goal_info, world.screen_text, source)
            context.add_evidence(items)
            extracted = "; ".join(i.value for i in items)
            return ActionOutcome(
                ok=True,
                data={"extracted": extracted, "evidence_count": len(items),
                      "evidence_labels": [i.label for i in items]},
            )

        return ActionOutcome(ok=False, error=f"Unknown action: {action}")

    def _ensure_focus(self, step: Step, state: ExecutionState) -> None:
        target = str(
            step.params.get("window")
            or step.params.get("app")
            or state.current_window
            or state.current_app
            or ""
        ).strip()
        if not target:
            return
        try:
            outcome = self._s.windows.focus(target)
            if outcome.ok:
                state.current_window = target
        except Exception:
            pass

    def _find_with_retry(self, query: str) -> Optional[UIElement]:
        """Resolve a query against the live world model. Cheap snapshots
        first; one vision escalation when the fast providers can't see it."""
        for attempt in range(self._config.find_retries):
            world = self._s.world.snapshot(force_refresh=attempt > 0)
            self._last_world = world
            element = self._s.world.find(world, query)
            if element is not None and element.has_position:
                return element
            if attempt == 1:
                # Escalate to full perception (vision LLM) once.
                try:
                    if self._exec_state is not None:
                        self._exec_state.vision_escalations += 1
                    world = self._s.world.snapshot(mode="full", force_refresh=True)
                    self._last_world = world
                    element = self._s.world.find(world, query)
                    if element is not None and element.has_position:
                        return element
                except Exception:
                    pass
            time.sleep(1)
        return None

    @staticmethod
    def _resolve_placeholder(text: str, context: TaskContext) -> str:
        lower = text.lower()
        is_placeholder = (
            not text
            or text in _PLACEHOLDER_LITERALS
            or "placeholder" in lower
            or ("title" in lower and len(text) < 20)
            or ("content" in lower and len(text) < 20)
        )
        if is_placeholder and context.latest_extraction:
            return context.latest_extraction
        return text

    # ------------------------------------------------------------ recovery

    def _recover(self, task: Task, failed: StepResult, context: TaskContext,
                 state: ExecutionState, rstate: ReasoningState,
                 executed: list[StepResult]) -> bool:
        """One RECOVER decision: bounded attempts of understand -> choose
        hypothesis -> act -> measure. Hypotheses rejected in earlier
        attempts are never chosen again."""
        step = failed.step
        reasoning = self._s.reasoning
        for attempt in range(1, self._config.max_healing_attempts + 1):
            if state.steps_executed >= self._config.max_steps:
                return False
            if state.healings >= self._config.max_recovery_total:
                return False
            state.healings += 1
            self._s.emit(EventType.HEALING_STARTED, task,
                         attempt=attempt, failed_step=step.description)

            try:
                world = self._perceive(task)
                reasoning.observe(rstate, world, self._s.world.last_diff, counted=False)
                diff = self._s.world.last_diff
                world_view = self._s.world.describe(world)
                if diff is not None and diff.summary:
                    # WHY before HOW: the diagnosis sees what changed since
                    # the failure (dialog appeared? focus moved? window gone?).
                    world_view += f"\nSince the failed step: {diff.summary}"
                plan = self._s.recovery.plan(
                    step, failed.error or "step failed", world_view, world, diff,
                    expected_window=state.current_window or state.current_app,
                    rejected_kinds=reasoning.rejected_kinds(rstate),
                )
            except Exception as e:
                self._s.emit(EventType.HEALING_RESULT, task, healed=False,
                             diagnosis=f"diagnosis failed: {e}")
                continue

            reasoning.record_recovery(rstate, plan, attempt)
            self._s.emit(
                EventType.HEALING_RESULT, task, healed=False,
                diagnosis=plan.chosen.explanation if plan.chosen else "no viable recovery",
                failure_type=plan.chosen.kind if plan.chosen else "unknown",
                confidence=plan.confidence, recovery_steps=len(plan.steps),
            )

            if not plan.steps:
                outcome = self._s.recovery.assess(plan, 0, False, False, False)
                reasoning.record_recovery_outcome(rstate, plan, outcome)
                time.sleep(1)
                continue

            all_ok = True
            steps_run = 0
            for recovery_step in plan.steps:
                if state.steps_executed >= self._config.max_steps:
                    all_ok = False
                    break
                recovery_step.source = "healer"  # runtime owns this invariant
                r = self._run_step(task, recovery_step, context, state, executed)
                steps_run += 1
                if not r.ok:
                    all_ok = False
                    break

            # Measure the recovery instead of assuming it: the original
            # failure condition must no longer hold in the fresh world.
            world_changed = False
            after: Optional[WorldState] = None
            try:
                after = self._perceive(task)
                reasoning.observe(rstate, after, self._s.world.last_diff, counted=False)
                world_changed = bool(self._s.world.last_diff and self._s.world.last_diff.changed)
            except Exception:
                pass
            condition_cleared = self._failure_condition_cleared(
                step, state, after, world_changed
            )

            outcome = self._s.recovery.assess(
                plan, steps_run, all_ok, world_changed, condition_cleared
            )

            if outcome.recovered and not self._plan_redid_original(plan.steps, step):
                # The cause is fixed but the original intent has not been
                # executed: retry it. Skipped when the recovery plan already
                # redid the action — retrying a click can double-submit.
                if state.steps_executed < self._config.max_steps:
                    retry = Step(action=step.action,
                                 description=f"retry: {step.description}",
                                 params=dict(step.params), source="healer")
                    r = self._run_step(task, retry, context, state, executed)
                    if not r.ok:
                        outcome.recovered = False
                        outcome.detail = "cause addressed but the retried step still fails"
                        if plan.chosen is not None:
                            plan.chosen.status = "rejected"
                            plan.chosen.resolution_reason = outcome.detail
                            plan.chosen.evidence_against.append(outcome.detail)
                else:
                    outcome.recovered = False
                    outcome.detail = "no step budget left to retry the original step"

            reasoning.record_recovery_outcome(rstate, plan, outcome)

            if outcome.recovered:
                self._s.emit(EventType.HEALING_RESULT, task, healed=True,
                             diagnosis=outcome.hypothesis_explanation)
                return True
            time.sleep(1)
        return False

    @staticmethod
    def _plan_redid_original(recovery_steps: list[Step], original: Step) -> bool:
        """Did the recovery plan already perform the failed step's intent?
        Same action with the same primary parameter counts."""
        keys = ("find", "text", "key", "app", "url", "window")
        original_params = {k: str(original.params.get(k, "")).strip().lower()
                           for k in keys if original.params.get(k)}
        for step in recovery_steps:
            if step.action != original.action:
                continue
            params = {k: str(step.params.get(k, "")).strip().lower()
                      for k in keys if step.params.get(k)}
            if original_params and params == original_params:
                return True
        return False

    def _failure_condition_cleared(self, failed_step: Step, state: ExecutionState,
                                   world: Optional[WorldState],
                                   world_changed: bool) -> bool:
        """Is the original failure demonstrably gone? Checkable per action:
        a missing element must now resolve, a missing window must now
        exist. When nothing is checkable we fall back to 'did the world
        change' — and when we could not observe at all, we cannot disprove
        the recovery, so it stands (verification still owns the verdict)."""
        if world is None:
            return True
        action, params = failed_step.action, failed_step.params

        if action == ActionType.CLICK:
            query = str(params.get("find", "")).strip()
            if query:
                element = self._s.world.find(world, query)
                return element is not None and element.has_position

        if action == ActionType.OPEN_APP:
            app = str(params.get("app", "")).strip()
            if app:
                return self._window_visible(app, world)

        if action in (ActionType.TYPE, ActionType.CLEAR_TYPE, ActionType.PRESS,
                      ActionType.FOCUS_WINDOW):
            target = str(
                params.get("window") or params.get("app")
                or state.current_window or state.current_app or ""
            ).strip()
            if target:
                return self._window_visible(target, world)

        return world_changed

    def _window_visible(self, keyword: str, world: WorldState) -> bool:
        needle = keyword.lower()
        if any(needle in w.title.lower() for w in world.windows):
            return True
        try:
            return self._s.windows.exists(keyword) is not None
        except Exception:
            return False

    # -------------------------------------------------------------- memory

    def _remember_interface(self, state: ExecutionState) -> None:
        """Perception memory: persist the fused elements of this app so
        future runs know its stable controls."""
        app = state.current_app or state.current_window
        if not app or self._last_world is None:
            return
        try:
            elements = [
                {
                    "text": el.name, "type": el.role,
                    "x": el.center[0], "y": el.center[1],
                    "confidence": el.confidence,
                }
                for el in self._last_world.elements
                if el.name and el.has_position
            ]
            self._s.memory.remember_interface(app, elements)
        except Exception:
            pass  # memory is best-effort; it never affects execution

    def _remember_element(self, state: ExecutionState, element: UIElement) -> None:
        """Reinforce a successfully used element identity."""
        app = state.current_app or state.current_window
        if not app or not element.name:
            return
        try:
            self._s.memory.remember_interface(
                app,
                [{"text": element.name, "type": element.role,
                  "x": element.center[0], "y": element.center[1],
                  "confidence": element.confidence}],
            )
        except Exception:
            pass

    # -------------------------------------------------------------- finish

    def _finish(self, task: Task, context: TaskContext, state: ExecutionState,
                executed: list[StepResult], rstate: Optional[ReasoningState],
                errors: list[str], started: float) -> TaskResult:
        state.llm_calls = int(getattr(self._s.llm, "calls", 0) or 0)
        duration = round(time.time() - started, 2)

        # Final observation: did the world actually change? Observe-only —
        # a snapshot reads the screen, it never touches focus or input.
        final_world: Optional[WorldState] = None
        if executed:
            try:
                final_world = self._s.world.snapshot(force_refresh=True)
                self._last_world = final_world
            except Exception:
                final_world = None

        try:
            verification = self._s.verifier.verify(
                context, executed,
                world_before=self._baseline_world, world_after=final_world,
            )
        except Exception as e:
            from .contracts import VerificationResult
            verification = VerificationResult(verified=False, reason=f"Verification unavailable: {e}")

        self._s.emit(
            EventType.VERIFICATION, task,
            verified=verification.verified, confidence=verification.confidence, reason=verification.reason,
        )

        # Steps superseded by a replan (SKIPPED) no longer define the
        # outcome: the goal was pursued along a different path, and
        # verification owns the verdict for that path.
        effective = [r for r in executed if r.status != StepStatus.SKIPPED]
        acted = bool(effective) or bool(rstate is not None and rstate.goal_achieved_signal)
        all_ok = acted and all(r.ok for r in effective) and not errors
        if not all_ok:
            status = TaskStatus.FAILED
        elif verification.verified:
            status = TaskStatus.COMPLETED
        else:
            status = TaskStatus.UNVERIFIED

        artifacts = []
        latest_shot = self._s.perception.latest_screenshot
        if latest_shot is not None:
            artifacts.append(Artifact(kind="screenshot", path=str(latest_shot), description="final screen state"))

        goal = context.goal
        if goal is None:
            from .contracts import GoalSpec
            goal = GoalSpec(intent=task.instruction, objectives=[task.instruction])

        try:
            report = self._s.reporter.build(
                goal, context, status, verification, artifacts,
                actions_summary=self._actions_summary(executed),
            )
        except Exception:
            from .contracts import TaskReport
            report = TaskReport(
                executive_summary=f"Task {status.value}: {task.instruction}. {verification.reason}.",
                evidence=list(context.evidence),
                confidence=verification.confidence,
                sources=list(context.sources),
                artifacts=artifacts,
            )

        metadata = {
            "replans": state.replans,
            "healings": state.healings,
            "llm_calls": state.llm_calls,
            "evidence_count": len(context.evidence),
            "sources": list(context.sources),
            "perception": self._perception_metadata(final_world),
        }
        if rstate is not None:
            try:
                metadata["reasoning"] = self._s.reasoning.summary(rstate)
            except Exception:
                pass

        result = TaskResult(
            task_id=task.id,
            instruction=task.instruction,
            status=status,
            summary=report.executive_summary,
            goal=goal,
            report=report,
            findings=list(context.evidence),
            artifacts=artifacts,
            steps=executed,
            verification=verification,
            duration_s=duration,
            errors=errors,
            confidence=report.confidence,
            metadata=metadata,
        )

        try:
            self._s.memory.remember_task(
                task.instruction,
                [r.to_dict() for r in executed],
                status == TaskStatus.COMPLETED,
                duration,
            )
            self._s.memory.remember_evidence(task.id, context.evidence)
        except Exception:
            pass

        self._s.emit(
            EventType.TASK_COMPLETED, task,
            status=status.value, duration_s=duration, total_steps=len(executed),
            verification=verification.to_dict(), summary=result.summary,
            report=report.to_dict(),
        )
        return result

    def _perception_metadata(self, final_world: Optional[WorldState]) -> dict:
        """Perception health for the result: snapshot counts, provider
        stats, and the final world confidence. Uncertainty is reported,
        never hidden."""
        try:
            meta = self._s.world.stats()
        except Exception:
            meta = {}
        if final_world is not None:
            meta["final_confidence"] = final_world.confidence
            meta["final_elements"] = len(final_world.elements)
            meta["final_windows"] = len(final_world.windows)
        return meta

    @staticmethod
    def _actions_summary(executed: list[StepResult]) -> str:
        apps = {
            str(r.step.params.get("app", "")).strip()
            for r in executed
            if r.step.action == ActionType.OPEN_APP and r.ok and r.step.params.get("app")
        }
        urls = {
            str(r.step.params.get("url", "")).strip()
            for r in executed
            if r.step.action == ActionType.NAVIGATE_URL and r.ok and r.step.params.get("url")
        }
        typed = sum(1 for r in executed if r.step.action in (ActionType.TYPE, ActionType.CLEAR_TYPE) and r.ok)
        parts = [f"{len(executed)} steps executed"]
        if apps:
            parts.append(f"apps opened: {', '.join(sorted(apps))}")
        if urls:
            parts.append(f"pages visited: {', '.join(sorted(urls))}")
        if typed:
            parts.append(f"{typed} text input(s)")
        return "; ".join(parts)
