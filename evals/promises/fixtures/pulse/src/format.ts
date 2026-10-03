export interface Summary {
  lineCount: number;
  longest: string;
}

export function summarize(text: string): Summary {
  const lines = text.split("\n");
  if (lines[lines.length - 1] === "") lines.pop();
  let longest = "";
  for (const line of lines) {
    if (line.length > longest.length) longest = line;
  }
  return { lineCount: lines.length, longest };
}

export function formatReport(summary: Summary): string[] {
  return [`lines: ${summary.lineCount}`, `longest: ${summary.longest}`];
}
