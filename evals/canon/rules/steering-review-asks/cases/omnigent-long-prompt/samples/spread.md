Long user prompts now collapse in `chatBubbleParts.tsx`.

The preview cuts by code point, `[...text].slice(0, limit).join("")`, so an emoji at the cut stays whole. Tests check the hidden tail and the Copy payload.
