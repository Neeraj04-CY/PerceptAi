export type Difficulty = "simple" | "medium" | "custom";

export interface PlaybookTemplate {
  id: string;
  category: "Research" | "Productivity" | "System" | "Custom";
  icon: string;
  title: string;
  description: string;
  instruction: string;
  estimatedTime: string;
  difficulty: Difficulty;
  hasInput?: boolean;
  inputLabel?: string;
  inputPlaceholder?: string;
}

export const templates: PlaybookTemplate[] = [
  {
    id: "hn-digest",
    category: "Research",
    icon: "📰",
    title: "HackerNews Digest",
    description: "Extract today's top stories from HackerNews",
    instruction:
      "open chrome, go to news.ycombinator.com, read the page, extract the top 5 story titles and their point counts",
    estimatedTime: "30s",
    difficulty: "simple",
  },
  {
    id: "notepad-notes",
    category: "Productivity",
    icon: "📝",
    title: "Quick Notes",
    description: "Open Notepad and write timestamped notes",
    instruction:
      "open notepad and write today's date and time as a header, then write 'Session started'",
    estimatedTime: "10s",
    difficulty: "simple",
  },
  {
    id: "web-research",
    category: "Research",
    icon: "🔍",
    title: "Web Research",
    description: "Navigate to any URL and extract page content",
    instruction:
      "open chrome, go to [URL], read the page and extract the main content",
    estimatedTime: "45s",
    difficulty: "medium",
    hasInput: true,
    inputLabel: "URL to research",
    inputPlaceholder: "https://example.com",
  },
  {
    id: "system-info",
    category: "System",
    icon: "💻",
    title: "System Check",
    description: "Open system info and capture current state",
    instruction:
      "press windows key, type 'system information', open it, wait for it to load",
    estimatedTime: "15s",
    difficulty: "simple",
  },
  {
    id: "daily-brief",
    category: "Research",
    icon: "🌅",
    title: "Daily Brief",
    description: "Open Chrome and check top AI news",
    instruction:
      "open chrome, go to techcrunch.com/category/artificial-intelligence, read the page, extract the 3 most recent article headlines",
    estimatedTime: "45s",
    difficulty: "medium",
  },
  {
    id: "custom",
    category: "Custom",
    icon: "⚡",
    title: "Custom Task",
    description: "Write your own instruction",
    instruction: "",
    estimatedTime: "varies",
    difficulty: "custom",
    hasInput: true,
    inputLabel: "Your instruction",
    inputPlaceholder: "Describe what you want the agent to do...",
  },
];

export function resolveInstruction(
  template: PlaybookTemplate,
  value: string
): string {
  if (!template.hasInput) return template.instruction;
  const v = value.trim();
  if (template.instruction.includes("[URL]")) {
    return template.instruction.replace(/\[URL\]/g, v);
  }
  return v || template.instruction;
}
