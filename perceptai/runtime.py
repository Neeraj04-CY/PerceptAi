"""The one execution loop.

perceive -> plan -> act -> verify, with incremental replanning after
anything that changes the screen, bounded healing on failure, and a
replan-from-live-screen escalation when healing fails. Every branch is
budgeted; every transition emits a canonical event.

Perception flows exclusively through the world model: the engine never
reads raw OCR. Every snapshot is a fused, confidence-scored WorldState;
element lookups, planner context, healing context and verification all
derive from it.
"""
from __future__ import annotations

import time
from collections import deque
from typing import TYPE_CHECKING, Optional

from .contracts import (
    ActionOutcome,
    ActionType,
    Artifact,
    ExecutionState,
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

if TYPE_CHECKING:
    from .session import AgentSession

_PLACEHOLDER_LITERALS = {"{{extract}}", "{extract}", "$extract", "extracted_text"}


class ExecutionEngine:
    def __init__(self, session: "AgentSession"):
        self._s = session
        self._config = session.config
        self._last_world: Optional[WorldState] = None
        self._baseline_world: Optional[WorldState] = None

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
        executed: list[StepResult] = []
        errors: list[str] = []

        self._s.emit(EventType.TASK_STARTED, task, instruction=task.instruction)

        self._understand_goal(task, context)

        try:
            initial = self._plan(task, context, executed, state, source="planner")
        except Exception as e:
            return self._finish(task, context, state, executed,
                                errors=[f"Planning failed: {e}"], started=start)

        if not initial:
            return self._finish(task, context, state, executed,
                                errors=["Could not plan task"], started=start)

        self._s.emit(
            EventType.PLAN_CREATED, task,
            steps=[{"description": s.description, "action": s.action.value} for s in initial],
        )

        queue = deque(initial)
        while state.steps_executed < self._config.max_steps:
            if not queue:
                continuation = self._continue_toward_goal(task, context, executed, state)
                if not continuation:
                    break
                queue = deque(continuation)
                continue

            step = queue.popleft()
            result = self._run_step(task, step, context, state, executed)

            if not result.ok:
                if self._heal(task, step, result, context, state, executed):
                    result.status = StepStatus.HEALED
                else:
                    replanned = self._replan(task, context, executed, state, reason="unhealed step failure")
                    if replanned:
                        queue = deque(replanned)
                        continue
                    errors.append(f"Step {result.index} failed and could not be healed: {result.error}")
                    break

            self._remember_interface(state)

            if step.action in (ActionType.OPEN_APP, ActionType.NAVIGATE_URL) and result.ok:
                settle = float(step.params.get("wait", self._config.settle_after_launch_s))
                self._s.emit(EventType.LOG, task, message=f"Waiting {settle}s for screen to settle...")
                time.sleep(settle)
                replanned = self._replan(task, context, executed, state, reason="screen changed after launch")
                if replanned:
                    queue = deque(replanned)

            time.sleep(self._config.settle_after_step_s)

        return self._finish(task, context, state, executed, errors=errors, started=start)

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

    def _continue_toward_goal(self, task: Task, context: TaskContext,
                              executed: list[StepResult], state: ExecutionState) -> Optional[list[Step]]:
        """The plan queue is empty. If the goal defines completion criteria,
        ask the planner whether more work is needed ([] = goal achieved).
        Bounded by the existing replan budget."""
        goal = context.goal
        if goal is None or not goal.completion_criteria:
            return None
        if not executed:  # nothing was ever executed; don't loop on an empty task
            return None
        return self._replan(task, context, executed, state, reason="checking goal completion")

    # ------------------------------------------------------------ planning

    def _plan(self, task: Task, context: TaskContext, executed: list[StepResult],
              state: ExecutionState, source: str) -> list[Step]:
        world = self._perceive(task)
        world_view = self._s.world.describe(world)
        world_view = self._append_known_controls(world_view, state)
        windows = [w.title for w in world.windows]
        if not windows:
            try:
                windows = self._s.windows.list_windows()
            except Exception:
                windows = []
        output = self._s.planner.plan(
            task.instruction, world_view, executed, windows,
            source=source, goal=context.goal, known_facts=context.facts,
        )
        return output.steps if output.ok else []

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
                state: ExecutionState, reason: str) -> Optional[list[Step]]:
        if state.replans >= self._config.max_replans:
            self._s.emit(EventType.LOG, task, message="Replan budget exhausted")
            return None
        state.replans += 1
        try:
            steps = self._plan(task, context, executed, state, source="replan")
        except Exception as e:
            self._s.emit(EventType.LOG, task, message=f"Replanning failed: {e}")
            return None
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
                # healing and replanning; a wrong click can cause real damage.
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

    # ------------------------------------------------------------- healing

    def _heal(self, task: Task, step: Step, result: StepResult, context: TaskContext,
              state: ExecutionState, executed: list[StepResult]) -> bool:
        for attempt in range(1, self._config.max_healing_attempts + 1):
            if state.steps_executed >= self._config.max_steps:
                return False
            state.healings += 1
            self._s.emit(EventType.HEALING_STARTED, task, attempt=attempt, failed_step=step.description)

            try:
                world = self._perceive(task)
                world_view = self._s.world.describe(world)
                diff = self._s.world.last_diff
                if diff is not None and diff.summary:
                    # WHY before HOW: the healer sees what changed since the
                    # failure (dialog appeared? focus moved? window closed?).
                    world_view += f"\nSince the failed step: {diff.summary}"
                plan = self._s.healer.diagnose(step, result.error or "step failed", world_view)
            except Exception as e:
                self._s.emit(EventType.HEALING_RESULT, task, healed=False, diagnosis=f"diagnosis failed: {e}")
                continue

            self._s.emit(
                EventType.HEALING_RESULT, task,
                healed=False, diagnosis=plan.diagnosis,
                failure_type=plan.failure_type, confidence=plan.confidence,
                recovery_steps=len(plan.steps),
            )

            if plan.steps and plan.confidence > self._config.healing_confidence_threshold:
                recovered = True
                for recovery_step in plan.steps:
                    if state.steps_executed >= self._config.max_steps:
                        recovered = False
                        break
                    recovery_step.source = "healer"  # runtime owns this invariant
                    r = self._run_step(task, recovery_step, context, state, executed)
                    if not r.ok:
                        recovered = False
                        break
                if recovered:
                    self._s.emit(EventType.HEALING_RESULT, task, healed=True, diagnosis=plan.diagnosis)
                    return True
            time.sleep(1)
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
                executed: list[StepResult], errors: list[str], started: float) -> TaskResult:
        state.llm_calls = self._s.llm.calls
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

        all_ok = bool(executed) and all(r.ok for r in executed) and not errors
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
            metadata={
                "replans": state.replans,
                "healings": state.healings,
                "llm_calls": state.llm_calls,
                "evidence_count": len(context.evidence),
                "sources": list(context.sources),
                "perception": self._perception_metadata(final_world),
            },
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
