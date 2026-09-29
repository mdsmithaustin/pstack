Long user prompts now collapse in `chatBubbleParts.tsx`.

Prompts over 8,000 characters render the first 8,000 characters with a fade and a "Show full prompt (N chars)" button, and "Collapse prompt" once expanded. Only the visible slice reaches the markdown renderer. Copy still writes the full prompt.

Tests in `chatBubbleParts.test.tsx` cover the short and long cases and the button labels.
