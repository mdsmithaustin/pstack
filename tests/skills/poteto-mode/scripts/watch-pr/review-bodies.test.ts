import { describe, expect, it } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import {
  buildReviewState,
  parseReviewStatePage,
} from "../../../../../skills/poteto-mode/scripts/watch-pr/github.ts";
import {
  HEADS,
  botReview,
  comment,
  realAckComment,
  restReviews,
  reviewBodiesResponse,
} from "./review-fixtures.test-helper.ts";
import type { RestComment, RestReview } from "./review-fixtures.test-helper.ts";

const COPILOT = "copilot-pull-request-reviewer";
const MARKER = "<!-- ccr-overview-v2 -->";
const OVERVIEW = `${MARKER}\n**Findings:** None`;

function flagged(args: {
  readonly head: string;
  readonly reviews: readonly RestReview[];
  readonly comments?: readonly RestComment[];
  readonly prAuthor?: string | null;
}) {
  const state = buildReviewState([
    parseReviewStatePage(
      reviewBodiesResponse({
        headRefOid: args.head,
        reviews: args.reviews,
        ...(args.comments === undefined ? {} : { comments: args.comments }),
        ...(args.prAuthor === undefined ? {} : { prAuthor: args.prAuthor }),
      })
    ),
  ]);
  return state;
}

const json = (value: unknown): unknown => JSON.parse(JSON.stringify(value));
const finding = (section: string, title: string, location: string | null) => ({
  section,
  title,
  location,
});

describe("review body classification over the real fixtures", () => {
  const none: null = null;
  const table: readonly [
    pr: keyof typeof HEADS,
    id: string,
    expected: ReturnType<typeof finding> | null,
  ][] = [
    [104, "5386322877", none],
    [104, "5386340917", none],
    [
      104,
      "5386371606",
      finding(
        "Previously missed",
        "Require listed model catalog to support requested reasoning effort",
        "skills/setup-pstack/scripts/check-models-config.py:108"
      ),
    ],
    [107, "5386573417", none],
    [107, "5386587770", none],
    [
      107,
      "5386669231",
      finding(
        "Previously missed",
        "Align none-effort lint claims with the static model table",
        "skills/setup-pstack/references/models-config.md:14"
      ),
    ],
    [107, "5386687443", none],
    [
      107,
      "5386703352",
      finding(
        "Previously missed",
        "Documentation overstates lint coverage for gpt-6.1-luna",
        "skills/setup-pstack/references/models-config.md:14"
      ),
    ],
    [107, "5386732704", none],
    [108, "5388102853", none],
    [108, "5388116138", none],
    [108, "5388116230", none],
    [108, "5388116311", none],
    [108, "5388116396", none],
    [
      108,
      "5388128492",
      finding(
        "Previously missed",
        "Porting invariant conflicts with unreworked cloud orchestration requirements",
        "PORTING.md:45"
      ),
    ],
    [351, "5697766820", none],
    [353, "5700131442", none],
    [
      353,
      "5700727173",
      finding(
        "previously missed issue",
        "Ignore counted summaries inside Markdown code literals",
        "skills/poteto-mode/scripts/watch-pr/review-bodies.ts:163"
      ),
    ],
    [353, "5701377075", none],
  ];

  it("covers every review in the fixture files", () => {
    for (const pr of [104, 107, 108, 351, 353] as const)
      expect(
        restReviews(pr).map((review) => review.html_url.split("-").pop())
      ).toEqual(table.filter(([row]) => row === pr).map(([, id]) => id));
  });

  for (const [pr, id, expected] of table)
    it(`#${pr} review ${id} at its own commit reports ${expected === null ? "no finding" : expected.title}`, () => {
      const review = restReviews(pr).find((row) => row.id === Number(id));
      if (review === undefined) throw new Error(`fixture lacks ${id}`);
      const state = flagged({ head: review.commit_id, reviews: [review] });
      expect(state.flaggedReviews.map((row) => row.findings)).toEqual(
        expected === null ? [] : [[expected]]
      );
    });

  it("never reads a user-authored review, even with a bot's findings in its body", () => {
    const body = restReviews(104)[2]?.body ?? "";
    const review = {
      ...botReview({ id: 9, commit: HEADS[104], body }),
      user: { login: "mdsmithaustin", type: "User" },
    };
    const state = flagged({ head: HEADS[104], reviews: [review] });
    expect(state.flaggedReviews).toEqual([]);
  });

  it("flags only the item without a thread link in #353 review 5701377075's open issues", () => {
    const review = restReviews(353).find((row) => row.id === 5701377075);
    if (review === undefined) throw new Error("fixture lacks 5701377075");
    const title = "Honor escaped backticks when detecting code spans";
    const link = `[${title}](https://github.com/mdsmithaustin/pstack/pull/353#discussion_r4415105466)`;
    const body = review.body.replace(link, title);
    const state = flagged({ head: review.commit_id, reviews: [{ ...review, body }] });
    expect(state.flaggedReviews.map((row) => row.findings)).toEqual([
      [finding("open issues", `${title} · New`, null)],
    ]);
  });
});

describe("which reviews count", () => {
  it("#104 flags only the Copilot review of the head, as an open review", () => {
    const state = flagged({ head: HEADS[104], reviews: restReviews(104) });
    expect(
      state.flaggedReviews.map((row) => [row.id, row.status, row.bot, row.commitOid])
    ).toEqual([["5386371606", "open", COPILOT, HEADS[104]]]);
    expect(state.flaggedReviews[0]?.url).toBe(
      "https://github.com/mdsmithaustin/pstack/pull/104#pullrequestreview-5386371606"
    );
  });

  it("#104 flags nothing once the head moves past that review's commit", () => {
    expect(
      flagged({ head: "f".repeat(40), reviews: restReviews(104) }).flaggedReviews
    ).toEqual([]);
  });

  it("#107 at its final head is clean, though two earlier passes had findings", () => {
    const state = flagged({ head: HEADS[107], reviews: restReviews(107) });
    expect(state.flaggedReviews).toEqual([]);
  });

  it("#108 at 3e3260b7 flags review 5388128492 as open", () => {
    const state = flagged({ head: HEADS[108], reviews: restReviews(108) });
    expect(json(state.flaggedReviews.map((row) => [row.id, row.status]))).toEqual([
      ["5388128492", "open"],
    ]);
  });

  it("skips a PENDING review", () => {
    const body = restReviews(104)[2]?.body ?? "";
    const review = botReview({ id: 5, commit: HEADS[104], body, state: "PENDING" });
    expect(flagged({ head: HEADS[104], reviews: [review] }).flaggedReviews).toEqual(
      []
    );
  });

  it("ignores the same bot's marked reviews of older commits", () => {
    const body = restReviews(104)[2]?.body ?? "";
    const reviews = [
      botReview({ id: 5, commit: HEADS[104], body }),
      ...Array.from({ length: 5 }, (_, index) =>
        botReview({ id: 10 + index, commit: "a".repeat(40), body: MARKER })
      ),
    ];
    expect(
      json(flagged({ head: HEADS[104], reviews }).flaggedReviews.map((row) => row.id))
    ).toEqual(["5"]);
  });
});

describe("acknowledging a flagged review", () => {
  const link = "https://github.com/mdsmithaustin/pstack/pull/104#pullrequestreview-5386371606";
  const statusOf = (
    comments: readonly RestComment[],
    prAuthor: string | null = "mdsmithaustin"
  ) =>
    flagged({
      head: HEADS[104],
      reviews: restReviews(104),
      comments,
      prAuthor,
    }).flaggedReviews.map((row) => row.status);

  it("accepts the PR author, whatever their association", () => {
    expect(
      statusOf([
        comment({ id: 1, body: `Disproof: ${link}`, login: "mdsmithaustin", association: "NONE" }),
      ])
    ).toEqual(["acknowledged"]);
  });

  it("accepts an OWNER, MEMBER, or COLLABORATOR who is not the author", () => {
    for (const association of ["OWNER", "MEMBER", "COLLABORATOR"])
      expect(
        statusOf([comment({ id: 1, body: `Fixed. ${link}`, login: "maintainer", association })])
      ).toEqual(["acknowledged"]);
  });

  it("records who acknowledged and where", () => {
    const state = flagged({
      head: HEADS[104],
      reviews: restReviews(104),
      comments: [
        comment({ id: 7, body: `Fixed. ${link}`, login: "maintainer", association: "MEMBER" }),
      ],
    });
    expect(state.flaggedReviews[0]).toMatchObject({
      status: "acknowledged",
      ack: {
        author: "maintainer",
        url: "https://github.com/owner/repo/pull/1#issuecomment-7",
      },
    });
  });

  it("rejects a bot, even one with write access", () => {
    expect(
      statusOf([
        comment({ id: 1, body: link, login: "helper", association: "MEMBER", type: "Bot" }),
      ])
    ).toEqual(["open"]);
  });

  it("rejects a commenter who is neither the author nor trusted", () => {
    for (const association of ["NONE", "CONTRIBUTOR", "FIRST_TIME_CONTRIBUTOR", "SOMETHING_NEW"])
      expect(
        statusOf([comment({ id: 1, body: link, login: "stranger", association })])
      ).toEqual(["open"]);
  });

  it("rejects a link to a longer review id that starts with the same digits", () => {
    expect(
      statusOf([
        comment({
          id: 1,
          body: `${link}0`,
          login: "mdsmithaustin",
          association: "OWNER",
        }),
      ])
    ).toEqual(["open"]);
  });

  it("rejects a bare review fragment without the full URL", () => {
    expect(
      statusOf([
        comment({
          id: 1,
          body: "Not fixed: #pullrequestreview-5386371606",
          login: "mdsmithaustin",
          association: "OWNER",
        }),
      ])
    ).toEqual(["open"]);
  });

  it("rejects another PR's URL that carries the same review id", () => {
    expect(
      statusOf([
        comment({
          id: 1,
          body: "https://github.com/mdsmithaustin/pstack/pull/105#pullrequestreview-5386371606",
          login: "mdsmithaustin",
          association: "OWNER",
        }),
      ])
    ).toEqual(["open"]);
  });

  it("rejects a URL whose review id merely starts with the flagged id", () => {
    const review = botReview({ id: 5, commit: "head", body: `${OVERVIEW}\n<details>\n<summary><strong>Previously missed (1)</strong></summary>\n</details>` });
    const statuses = (body: string) =>
      flagged({
        head: "head",
        reviews: [review],
        comments: [comment({ id: 1, body, login: "mdsmithaustin", association: "OWNER" })],
      }).flaggedReviews.map((row) => row.status);
    expect(statuses("https://github.com/owner/repo/pull/1#pullrequestreview-50")).toEqual(["open"]);
    expect(statuses("https://github.com/owner/repo/pull/1#pullrequestreview-5")).toEqual(["acknowledged"]);
  });

  it("accepts the full URL as a Markdown link destination", () => {
    expect(
      statusOf([
        comment({
          id: 1,
          body: `Valid, fixed in abc123 ([review](${link})).`,
          login: "mdsmithaustin",
          association: "OWNER",
        }),
      ])
    ).toEqual(["acknowledged"]);
  });

  it("rejects a pr-recap comment that links the review", () => {
    expect(
      statusOf([
        comment({
          id: 1,
          body: `\n<!-- pstack-recap:start -->\nReviewed in [Copilot's pass](${link}).\n<!-- pstack-recap:end -->`,
          login: "mdsmithaustin",
          association: "OWNER",
        }),
      ])
    ).toEqual(["open"]);
  });

  describe("the comment the pr-recap skill writes", () => {
    const skill = join(import.meta.dir, "../../../../../skills/pr-recap");
    const block = readFileSync(join(skill, "references/block.md"), "utf8");
    const template = block.match(/````markdown\n([\s\S]*?)\n````/)?.[1] ?? "";

    it("never acknowledges a review, even when it names the review's URL", () => {
      expect(template).toStartWith("<!-- pstack-recap:start -->");
      expect(
        statusOf([
          comment({
            id: 1,
            body: `${template}\n\nReviewed: ${link}`,
            login: "mdsmithaustin",
            association: "OWNER",
          }),
        ])
      ).toEqual(["open"]);
    });
  });

  it("rejects a comment that mentions the review without linking it", () => {
    expect(
      statusOf([
        comment({
          id: 1,
          body: "Follow-up on Copilot's second review of this PR (22:28Z): fixed in abc123.",
          login: "mdsmithaustin",
          association: "OWNER",
        }),
      ])
    ).toEqual(["open"]);
  });

  it("clears the real #108 review with its real acknowledgment comment", () => {
    const state = flagged({
      head: HEADS[108],
      reviews: restReviews(108),
      comments: [realAckComment()],
      prAuthor: "mdsmithaustin",
    });
    expect(state.flaggedReviews).toMatchObject([
      {
        id: "5388128492",
        status: "acknowledged",
        ack: {
          author: "mdsmithaustin",
          url: "https://github.com/mdsmithaustin/pstack/pull/108#issuecomment-5945280704",
        },
      },
    ]);
  });
});

describe("bodies in any format", () => {
  const at = (body: string, login = COPILOT) =>
    flagged({
      head: "head",
      reviews: [botReview({ id: 77, commit: "head", body, login })],
    });

  it("reads a body with no counted section as clean, from Copilot or any other bot", () => {
    expect(at("## Copilot code review v3\n\nLooks risky.\n").flaggedReviews).toEqual([]);
    expect(
      at("Bugbot reviewed your changes and found no bugs!", "cursor-bugbot").flaggedReviews
    ).toEqual([]);
  });

  it("reads plain counted summaries and headings as clean", () => {
    for (const body of [
      "<summary>📒 Files selected for processing (5)</summary>",
      "<summary>Files not reviewed (2)</summary>",
      "### Suppressed comments (2)",
    ])
      expect(at(body).flaggedReviews).toEqual([]);
  });

  it("keeps both Open items across a fenced code block with a counted heading", () => {
    const body = "<summary><strong>Open (2)</strong></summary>\n- First item\n```\n# x (3)\n```\n- Second item";
    expect(at(body).flaggedReviews.map((row) => row.findings)).toEqual([
      [finding("Open", "First item", null), finding("Open", "Second item", null)],
    ]);
  });

  it("keeps both Open items across a counted Details heading", () => {
    const body = "<summary><strong>Open (2)</strong></summary>\n- First item\n### Details (1)\n- Second item";
    expect(at(body).flaggedReviews.map((row) => row.findings)).toEqual([
      [finding("Open", "First item", null), finding("Open", "Second item", null)],
    ]);
  });

  it("keeps a counted nested summary as an item title", () => {
    const body = "<summary><strong>Previously missed (1)</strong></summary>\n<details><summary>Item title (2)</summary>body</details>";
    expect(at(body).flaggedReviews.map((row) => row.findings)).toEqual([
      [finding("Previously missed", "Item title (2)", null)],
    ]);
  });

  it("flags a threadless counted section from any bot, with or without the Copilot marker", () => {
    const section = `<details>\n<summary><strong>Previously missed (1)</strong></summary>\n</details>`;
    for (const body of [section, `${OVERVIEW}\n${section}`])
      expect(at(body, "cursor-bugbot").flaggedReviews).toMatchObject([
        { id: "77", bot: "cursor-bugbot", status: "open" },
      ]);
  });

  it("treats an empty or blank body as clean for every bot", () => {
    for (const login of [COPILOT, "cursor-bugbot"]) {
      expect(at("  \n", login).flaggedReviews).toEqual([]);
    }
  });

  it("counts every item of an unknown section", () => {
    const body = `${OVERVIEW}\n<details>\n<summary><strong>Low confidence (2)</strong></summary>\n</details>`;
    expect(at(body).flaggedReviews).toMatchObject([
      {
        findings: [
          { section: "Low confidence", title: "(unparsed)", location: null },
          { section: "Low confidence", title: "(unparsed)", location: null },
        ],
      },
    ]);
  });

  it("leaves thread-linked Open items and Resolved items to the thread gate", () => {
    const body = `${OVERVIEW}\n<details open>\n<summary><strong>Open (1)</strong></summary>\n\n- [Rename it](#discussion_r42) · New\n</details>\n<details>\n<summary><strong>Resolved since last review (2)</strong></summary>\n\n- [Done](#discussion_r41)\n</details>`;
    expect(at(body).flaggedReviews).toEqual([]);
  });

  it("reads an Open section by its first word in any case and either count form", () => {
    for (const [heading, name] of [
      ["open (1)", "open"],
      ["1 Open issue", "Open issue"],
      ["1 open issue", "open issue"],
      ["1 OPEN", "OPEN"],
    ]) {
      const section = `<summary><strong>${heading}</strong></summary>\n\n`;
      expect(at(`${section}- [Linked](#discussion_r42)\n`).flaggedReviews).toEqual([]);
      expect(at(`${section}- Loose item\n`).flaggedReviews.map((row) => row.findings)).toEqual([
        [finding(name, "Loose item", null)],
      ]);
    }
  });

  it("flags a counted Open section in a body without a Findings line", () => {
    const body = `${MARKER}\n\n## Copilot review overview\n\n<details>\n<summary><strong>Open (1)</strong></summary>\n</details>\n`;
    expect(at(body).flaggedReviews).toMatchObject([
      { status: "open", findings: [{ section: "Open", title: "(unparsed)" }] },
    ]);
  });

  it("reads a marked body with a Findings line and no counted section as clean", () => {
    expect(at(`${MARKER}\n\n**Findings:** None\n`).flaggedReviews).toEqual([]);
    expect(at(`${MARKER}\n\n**Findings:** 2 <b>x</b>\n`).flaggedReviews).toEqual([]);
  });

  it("bounds the finding count a body claims, in sections and in Open", () => {
    for (const section of ["Previously missed", "Open"]) {
      const body = `${OVERVIEW}\n<details>\n<summary><strong>${section} (99999999999)</strong></summary>\n</details>`;
      const [row] = at(body).flaggedReviews;
      expect(row?.findings.length).toBe(20);
    }
  });

  it("bounds a section count too large for a number", () => {
    const body = `${OVERVIEW}\n<details>\n<summary><strong>Previously missed (${"9".repeat(400)})</strong></summary>\n</details>`;
    const [row] = at(body).flaggedReviews;
    expect(row?.status).toBe("open");
    expect(row?.findings.length).toBe(20);
  });

  it("keeps the text around a stray angle bracket in a title", () => {
    const body = `${OVERVIEW}\n<details open>\n<summary><strong>Open (1)</strong></summary>\n\n- Handle a < b and c > d\n</details>`;
    expect(at(body).flaggedReviews).toMatchObject([
      { findings: [{ title: "Handle a < b and c > d" }] },
    ]);
  });

  it("strips tags that only appear once an inner tag is removed", () => {
    const body = `${OVERVIEW}\n<details open>\n<summary><strong>Open (2)</strong></summary>\n\n- <<b>script>alert(1)</b>\n- tail <script\n</details>`;
    expect(at(body).flaggedReviews).toMatchObject([
      {
        findings: [{ title: "alert(1)" }, { title: "tail script" }],
      },
    ]);
  });

  it("flags an unparsed finding when an Open section's items are not list lines", () => {
    const body = `${OVERVIEW}\n<details open>\n<summary><strong>Open (1)</strong></summary>\n<details><summary>Nested item</summary>body</details>\n</details>`;
    expect(at(body).flaggedReviews).toMatchObject([
      {
        findings: [{ section: "Open", title: "(unparsed)", location: null }],
      },
    ]);
  });

  it("pads an Open section up to its count when some items are thread-linked", () => {
    const body = `${OVERVIEW}\n<details open>\n<summary><strong>Open (3)</strong></summary>\n\n- [Linked](#discussion_r42)\n- Loose item\n</details>`;
    expect(at(body).flaggedReviews).toMatchObject([
      {
        findings: [{ title: "Loose item" }, { title: "(unparsed)" }],
      },
    ]);
  });

  it("flags an Open item that only mentions a thread id, without a link destination", () => {
    const body = `${OVERVIEW}\n<details open>\n<summary><strong>Open (2)</strong></summary>\n\n- [Mention #discussion_r42 in the docs](#something)\n- Mention #discussion_r42 in the docs\n</details>`;
    expect(at(body).flaggedReviews).toMatchObject([
      {
        findings: [
          { title: "[Mention #discussion_r42 in the docs](#something)" },
          { title: "Mention #discussion_r42 in the docs" },
        ],
      },
    ]);
  });

  it("skips an Open item whose link destination is a review thread", () => {
    const body = `${OVERVIEW}\n<details open>\n<summary><strong>Open (2)</strong></summary>\n\n- [Rename it](#discussion_r123) · New\n- [Rename that](https://github.com/o/r/pull/1#discussion_r456)\n</details>`;
    expect(at(body).flaggedReviews).toEqual([]);
  });

  it("reads a leading count as a counted section, with its nested items", () => {
    const body = `${MARKER}\n<details>\n<summary><strong>2 previously missed issues</strong></summary>\n\n<details>\n<summary>First</summary>\n\n\`a.ts:1\`\n</details>\n<details>\n<summary>Second</summary>\n</details>\n</details>`;
    expect(at(body).flaggedReviews.map((row) => row.findings)).toEqual([
      [
        finding("previously missed issues", "First", "a.ts:1"),
        finding("previously missed issues", "Second", null),
      ],
    ]);
  });

  it("reads a zero or Resolved section as clean in either count form", () => {
    for (const heading of [
      "0 previously missed issues",
      "2 resolved issues",
      "Resolved since last review (2)",
    ])
      expect(
        at(`<summary><strong>${heading}</strong></summary>\n<details><summary>Done</summary></details>`)
          .flaggedReviews
      ).toEqual([]);
  });

  describe("markup inside Markdown code", () => {
    const literal = "<summary><strong>Open (1)</strong></summary>";

    it("reads a counted summary in fenced code as clean", () => {
      for (const fence of ["```", "~~~"])
        expect(at(`Example:\n\n${fence}html\n${literal}\n${fence}\n`).flaggedReviews).toEqual([]);
    });

    it("still reads a finding after a line starting with a triple-backtick code span", () => {
      const body = "```x``` here\n\n<details><summary><strong>1 previously missed issue</strong></summary>\n<details><summary>Real</summary>body</details>\n</details>";
      expect(at(body).flaggedReviews.map((row) => row.findings)).toEqual([
        [finding("previously missed issue", "Real", null)],
      ]);
    });

    it("reads a counted summary in inline code as clean", () => {
      expect(at(`A body may quote \`${literal}\` in prose.\n`).flaggedReviews).toEqual([]);
      expect(at(`Doubled: \`\` ${literal} \`\` too.\n`).flaggedReviews).toEqual([]);
    });

    it("still reads a counted summary after a closed code span", () => {
      expect(at(`Quote \`x\`.\n\n<summary><strong>Previously missed (1)</strong></summary>\n`).flaggedReviews).toMatchObject([
        { findings: [{ section: "Previously missed", title: "(unparsed)" }] },
      ]);
    });

    it("keeps a section whole across a heading in fenced code", () => {
      const body = "<summary><strong>Open (2)</strong></summary>\n- First item\n```\n<summary><strong>Notes</strong></summary>\n```\n- Second item";
      expect(at(body).flaggedReviews.map((row) => row.findings)).toEqual([
        [finding("Open", "First item", null), finding("Open", "Second item", null)],
      ]);
    });

    it("ignores a nested summary quoted in an item's text", () => {
      const body = "<summary><strong>Previously missed (1)</strong></summary>\n<details><summary>Real</summary>\n\nQuotes `<summary>Fake</summary>` at `a.ts:3`\n</details>";
      expect(at(body).flaggedReviews.map((row) => row.findings)).toEqual([
        [finding("Previously missed", "Real", "a.ts:3")],
      ]);
    });

    it("ignores list lines in fenced code inside an Open section", () => {
      const body = "<summary><strong>Open (1)</strong></summary>\n\n- [Rename it](#discussion_r42)\n\n```\n- not an item\n```\n";
      expect(at(body).flaggedReviews).toEqual([]);
    });

    const missed = "<details><summary><strong>1 previously missed issue</strong></summary>\n<details><summary>Real</summary>body</details>\n</details>";
    const real: [[ReturnType<typeof finding>]] = [[finding("previously missed issue", "Real", null)]];

    it("still reads a finding after a fence that opens on a list marker", () => {
      for (const body of [
        `- \`\`\`js\n  const x = 1;\n  \`\`\`\n\n${missed}`,
        `1. Example:\n   \`\`\`js\n   const x = 1;\n   \`\`\`\n\n${missed}`,
        `- \`\`\`js\n  const x = 1;\n${missed}`,
      ])
        expect(at(body).flaggedReviews.map((row) => row.findings)).toEqual(real);
    });

    it("still reads a finding between lines with backslash-escaped backticks", () => {
      const body = `Escape a \\\` like this.\n${missed}\nAnd \\\` again.\n`;
      expect(at(body).flaggedReviews.map((row) => row.findings)).toEqual(real);
    });

    it("reads a counted summary in a fence inside a list item as clean", () => {
      for (const body of [
        `1.  Example:\n\n    \`\`\`html\n    ${literal}\n\n    \`\`\`\n`,
        `- Example:\n\n  - Nested:\n\n    ~~~\n    ${literal}\n    ~~~\n`,
      ])
        expect(at(body).flaggedReviews).toEqual([]);
    });

    it("keeps a backtick fence open past a line that mixes in a tilde", () => {
      expect(at(`\`\`\`\n\`\`\`~\n${literal}\n\`\`\`\n`).flaggedReviews).toEqual([]);
      expect(at(`~~~\n~~~\`\n${literal}\n~~~\n`).flaggedReviews).toEqual([]);
    });

    it("reads a counted summary after an unclosed fence as clean", () => {
      expect(at(`Example:\n\n\`\`\`html\n${literal}\n`).flaggedReviews).toEqual([]);
    });

    it("closes a fence on a longer run of the same character", () => {
      expect(at(`\`\`\`\n${literal}\n\`\`\`\`\n\n${missed}`).flaggedReviews.map((row) => row.findings)).toEqual(real);
    });

    it("does not let a code span cross a blank line", () => {
      const body = `A stray \` in prose.\n\n${missed}\n\nAnother \` here.\n`;
      expect(at(body).flaggedReviews.map((row) => row.findings)).toEqual(real);
    });

    it("does not take a thread link quoted in code as the item's thread", () => {
      const body = "<summary><strong>Open (1)</strong></summary>\n\n- Mention `[x](#discussion_r42)` in docs\n";
      expect(at(body).flaggedReviews).toMatchObject([
        { findings: [{ section: "Open", title: "Mention `[x](#discussion_r42)` in docs" }] },
      ]);
    });
  });

  it("flags an Open item that no thread carries", () => {
    const body = `${OVERVIEW}\n<details open>\n<summary><strong>Open (1)</strong></summary>\n\n- Needs a thread-less look\n</details>`;
    expect(at(body).flaggedReviews).toMatchObject([
      {
        findings: [{ section: "Open", title: "Needs a thread-less look", location: null }],
      },
    ]);
  });
});
