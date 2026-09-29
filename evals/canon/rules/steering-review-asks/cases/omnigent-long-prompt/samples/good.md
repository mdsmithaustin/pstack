Long user prompts now collapse in `chatBubbleParts.tsx`.

Prompts over 12,000 characters render a preview with a bottom fade and a "Show full prompt" button, and "Collapse prompt" once expanded. Only the visible slice reaches the markdown renderer. The slice drops a trailing high surrogate, so an emoji at the cut never renders as a broken character, and it never expands the whole prompt into code points. Copy still writes the full prompt.

Tests in `chatBubbleParts.test.tsx` put a unique marker past the cut and check it is absent while collapsed, present when expanded, absent again after collapsing, and in the Copy payload.
