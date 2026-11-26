"""Draws the architecture diagrams as SVG files.

Run from the project root:  python3 docs/diagrams/build.py
Edit the layout below and run again to change a diagram.
"""

from html import escape
from pathlib import Path

OUT = Path(__file__).parent
FONT = "system-ui, -apple-system, 'Segoe UI', Roboto, 'Noto Sans', 'Noto Sans Devanagari', sans-serif"
INK, MUTED, LINE = "#16181d", "#596070", "#68707f"

# Block colours by kind: (fill, border)
KINDS = {
    "browser": ("#e8f1fd", "#2f7fd8"),
    "transport": ("#f0ecfd", "#7058d6"),
    "agent": ("#e3f6f1", "#0f9c7e"),
    "ai": ("#fff0e5", "#e2711d"),
    "api": ("#fdf6dc", "#bd8b00"),
    "data": ("#eef0f3", "#707887"),
    "plain": ("#ffffff", "#c3c9d3"),
    "good": ("#e5f7e7", "#1a8f2e"),
    "bad": ("#fdeaea", "#d03b3c"),
}


class Drawing:
    def __init__(self, width: int, height: int, title: str, subtitle: str) -> None:
        self.width, self.height, self.title = width, height, title
        self.shapes: list[str] = []
        self.lines: list[str] = []
        self.top: list[str] = []
        self.text(40, 44, title, 24, weight=700)
        self.text(40, 70, subtitle, 14, MUTED)

    def text(self, x, y, value, size=13, colour=INK, weight=400, anchor="start", layer=None):
        (self.shapes if layer is None else layer).append(
            f'<text x="{x}" y="{y}" font-size="{size}" fill="{colour}" '
            f'font-weight="{weight}" text-anchor="{anchor}">{escape(value)}</text>'
        )

    def group(self, x, y, w, h, label, kind):
        fill, border = KINDS[kind]
        self.shapes.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="{fill}" '
            f'fill-opacity="0.35" stroke="{border}" stroke-width="1.5" stroke-dasharray="2 4"/>'
        )
        self.text(x + 16, y + 25, label.upper(), 12, border, 700)

    def box(self, x, y, w, h, title, lines=(), kind="plain"):
        fill, border = KINDS[kind]
        self.shapes.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" '
            f'stroke="{border}" stroke-width="1.8" data-box="1"/>'
        )
        block = 18 + 17 * len(lines)
        first = y + (h - block) / 2 + 14
        centre = x + w / 2
        self.text(centre, first, title, 14.5, weight=650, anchor="middle")
        for i, line in enumerate(lines):
            self.text(centre, first + 19 + 17 * i, line, 12.5, MUTED, anchor="middle")

    def arrow(self, *points, both=False, dashed=False, colour=LINE):
        path = "M " + " L ".join(f"{x} {y}" for x, y in points)
        marker = "dash" if dashed else "solid"
        start = f' marker-start="url(#{marker})"' if both else ""
        dash = ' stroke-dasharray="7 5"' if dashed else ""
        self.lines.append(
            f'<path d="{path}" fill="none" stroke="{colour}" stroke-width="2" '
            f'stroke-linejoin="round"{dash} marker-end="url(#{marker})"{start}/>'
        )

    def label(self, x, y, value):
        """Text on a white plate, so it stays readable where it crosses a line."""
        width = len(value) * 6.4 + 14
        self.top.append(
            f'<rect x="{x - width / 2}" y="{y - 12}" width="{width}" height="17" rx="5" '
            f'fill="#ffffff" fill-opacity="0.94"/>'
        )
        self.text(x, y + 1, value, 11.5, MUTED, 550, "middle", self.top)

    def step(self, x, y, number):
        self.top.append(f'<circle cx="{x}" cy="{y}" r="12" fill="#1b64be" stroke="#fff" stroke-width="2"/>')
        self.text(x, y + 4.5, str(number), 12.5, "#ffffff", 700, "middle", self.top)

    def save(self, name: str) -> None:
        markers = "".join(
            f'<marker id="{key}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
            f'markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" '
            f'fill="{LINE}"/></marker>'
            for key in ("solid", "dash")
        )
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} {self.height}" '
            f'width="{self.width}" height="{self.height}" font-family="{FONT}" role="img" '
            f'aria-label="{escape(self.title)}">\n<defs>{markers}</defs>\n'
            f'<rect width="100%" height="100%" rx="14" fill="#ffffff"/>\n'
            + "\n".join(self.shapes + self.lines + self.top)
            + "\n</svg>\n"
        )
        (OUT / name).write_text(svg, encoding="utf-8")


def overview() -> None:
    d = Drawing(1400, 930, "System overview",
                "Follow the numbers for one reply. Dashed lines run in the background.")
    d.group(30, 100, 250, 410, "Browser · Next.js", "browser")
    d.group(560, 100, 330, 510, "Voice agent · Python", "agent")
    d.group(1020, 100, 350, 510, "External AI services", "ai")
    d.group(300, 655, 590, 140, "API server · FastAPI", "api")

    d.box(50, 140, 210, 70, "Microphone & speaker", ["The caller"], "browser")
    d.box(50, 300, 210, 70, "Live panels", ["Transcript, lead, sources"], "browser")
    d.box(50, 410, 210, 70, "Document upload", ["Product files"], "browser")
    d.box(340, 140, 160, 230, "LiveKit server", ["Real-time room", "Audio and", "messages"], "transport")
    d.box(590, 140, 270, 65, "Agent session", ["Runs the voice pipeline"], "agent")
    d.box(590, 230, 270, 60, "Silero VAD", ["Detects interruptions"], "agent")
    d.box(590, 335, 270, 90, "Sales assistant", ["Language, memory,", "document passages"], "agent")
    d.box(590, 500, 270, 80, "Live intelligence", ["Lead facts, score, sentiment"], "agent")
    d.box(1050, 130, 290, 65, "Sarvam speech-to-text", ["saaras:v4 · detects language"], "ai")
    d.box(1050, 220, 290, 65, "Sarvam text-to-speech", ["bulbul:v4-flash · English / Hindi"], "ai")
    d.box(1050, 348, 290, 65, "Gemini · live reply", ["3.5 Flash-Lite"], "ai")
    d.box(1050, 508, 290, 65, "Gemini · analysis", ["Facts, sentiment, summary"], "ai")
    d.box(320, 695, 170, 75, "Calls & tokens", ["Consent, room access"], "api")
    d.box(515, 695, 190, 75, "Documents & search", ["Hybrid retrieval"], "api")
    d.box(730, 695, 145, 75, "E5 embeddings", ["Runs locally"], "api")
    d.box(515, 835, 190, 60, "knowledge.db", ["Passages and vectors"], "data")
    d.box(930, 700, 190, 65, "leads.db", ["Leads, calls, transcripts"], "data")

    d.arrow((260, 175), (340, 175), both=True)
    d.label(300, 162, "voice")
    d.arrow((340, 335), (260, 335))
    d.label(300, 322, "updates")
    d.arrow((500, 172), (590, 172), both=True)
    d.arrow((725, 205), (725, 230), both=True)
    d.arrow((860, 158), (1050, 158), both=True)
    d.label(955, 145, "audio → text")
    d.arrow((860, 190), (955, 190), (955, 252), (1050, 252), both=True)
    d.label(955, 224, "text → audio")
    d.arrow((590, 195), (574, 195), (574, 358), (590, 358))
    d.arrow((860, 380), (1050, 380), both=True)
    d.label(955, 367, "prompt → reply")
    d.arrow((590, 400), (535, 400), (535, 632), (610, 632), (610, 695), both=True)
    d.label(535, 520, "search")
    d.arrow((860, 540), (1050, 540), both=True, dashed=True)
    d.label(955, 527, "caller turns")
    d.arrow((725, 500), (725, 425), dashed=True)
    d.label(725, 466, "facts + next question")
    d.arrow((810, 580), (810, 632), (1025, 632), (1025, 700), dashed=True)
    d.label(940, 632, "save score")
    d.arrow((155, 480), (155, 732), (300, 732), both=True)
    d.label(155, 620, "HTTP requests")
    d.arrow((705, 732), (730, 732), both=True)
    d.arrow((610, 770), (610, 835), both=True)

    for x, y, n in ((300, 196, 1), (545, 172, 2), (894, 158, 3), (535, 470, 4), (894, 380, 5), (894, 190, 6)):
        d.step(x, y, n)

    d.text(1150, 668, "Key", 13, weight=700)
    for i, (n, value) in enumerate([
        (1, "Caller speaks"), (2, "Audio reaches the agent"), (3, "Speech becomes text"),
        (4, "Documents are searched"), (5, "Gemini writes the reply"), (6, "Reply becomes speech"),
    ]):
        d.step(1162, 692 + 31 * i, n)
        d.text(1182, 697 + 31 * i, value, 12.5)
    d.arrow((1150, 882), (1195, 882))
    d.text(1205, 886, "live path", 12, MUTED)
    d.arrow((1272, 882), (1317, 882), dashed=True)
    d.text(1325, 886, "later", 12, MUTED)
    d.save("1-system-overview.svg")


def conversation() -> None:
    d = Drawing(1400, 700, "One conversation turn",
                "What happens between the caller finishing a sentence and hearing the answer.")
    top = [
        ("Caller speaks", ["Browser microphone", "English, Hindi", "or Hinglish"], "browser"),
        ("LiveKit", ["Streams the audio", "to the voice agent"], "transport"),
        ("Speech-to-text", ["Sarvam", "Transcript, language,", "end of speech"], "ai"),
        ("Prepare the turn", ["Pick the language,", "add memory and", "known lead facts"], "agent"),
    ]
    bottom = [
        ("Search documents", ["API + E5 model", "Up to 4 passages,", "0.8 s time limit"], "api"),
        ("Write the reply", ["Gemini", "Answers from the", "passages"], "ai"),
        ("Text-to-speech", ["Sarvam", "Speaks as the text", "arrives"], "ai"),
        ("Caller hears it", ["Can interrupt", "at any time"], "browser"),
    ]
    xs = [60, 400, 740, 1080]
    for i, (title, lines, kind) in enumerate(top):
        d.box(xs[i], 130, 260, 125, title, lines, kind)
        d.step(xs[i] + 4, 134, i + 1)
        if i < 3:
            d.arrow((xs[i] + 260, 192), (xs[i + 1], 192))
    # The second row runs right to left.
    for i, (title, lines, kind) in enumerate(bottom):
        x = xs[3 - i]
        d.box(x, 320, 260, 125, title, lines, kind)
        d.step(x + 4, 324, i + 5)
        if i < 3:
            d.arrow((x, 382), (xs[2 - i] + 260, 382))
    d.arrow((1210, 255), (1210, 320))

    d.group(40, 485, 1320, 135, "In the background · the caller does not wait", "agent")
    chain = [("Caller's words", ["Queued after each turn"]), ("Gemini analysis", ["Facts and sentiment"]),
             ("Scoring rules", ["Score out of 100"]), ("Lead panel & database", ["Next question for the agent"])]
    for i, (title, lines) in enumerate(chain):
        d.box(xs[i], 525, 260, 70, title, lines, "ai" if i == 1 else "agent")
        if i < 3:
            d.arrow((xs[i] + 260, 560), (xs[i + 1], 560), dashed=True)

    d.text(40, 655, "Interruption: if the caller talks for 0.5 s or more while the agent speaks, "
                    "the voice stops and the new question is handled.", 13.5)
    d.text(40, 678, "One simulated call measured 3.2 to 4.3 s before the reply began. "
                    "The design target of 1.5 s is not yet met.", 13.5, MUTED)
    d.save("2-conversation-turn.svg")


def retrieval() -> None:
    d = Drawing(1400, 690, "Knowledge retrieval (RAG)",
                "Documents are indexed once. Each question is then matched against them.")
    d.group(30, 100, 1340, 175, "A · When a document is uploaded", "api")
    steps = [("Upload", ["PDF, DOCX, MD, TXT", "up to 5 MB"], "browser"),
             ("Extract text", ["pypdf and", "python-docx"], "api"),
             ("Split into passages", ["Up to 220 words,", "headings kept"], "api"),
             ("Create vectors", ["multilingual-e5-large", "runs locally"], "api"),
             ("Store", ["knowledge.db: text,", "vectors, keywords"], "data")]
    for i, (title, lines, kind) in enumerate(steps):
        x = 55 + 268 * i
        d.box(x, 145, 220, 100, title, lines, kind)
        d.step(x + 4, 149, i + 1)
        if i < 4:
            d.arrow((x + 220, 195), (x + 268, 195))

    d.group(30, 300, 1340, 360, "B · When the caller asks a question", "agent")
    d.box(55, 420, 210, 100, "Question", ["Growth plan की", "कीमत कितनी है?"], "browser")
    d.box(335, 345, 230, 90, "Meaning search", ["Compare vectors,", "best 20"], "agent")
    d.box(335, 505, 230, 90, "Keyword search", ["BM25 word match,", "best 20"], "agent")
    d.box(635, 420, 210, 100, "Merge rankings", ["Reciprocal rank", "fusion"], "agent")
    d.box(915, 420, 190, 100, "Close enough?", ["Similarity", "0.78 or higher"], "plain")
    d.box(1170, 345, 180, 100, "Yes", ["Top 4 passages", "go to Gemini,", "which answers"], "good")
    d.box(1170, 505, 180, 100, "No", ["Defer to a", "specialist; log", "the question"], "bad")
    d.arrow((265, 455), (300, 455), (300, 390), (335, 390))
    d.arrow((265, 485), (300, 485), (300, 550), (335, 550))
    d.arrow((565, 390), (600, 390), (600, 455), (635, 455))
    d.arrow((565, 550), (600, 550), (600, 485), (635, 485))
    d.arrow((845, 470), (915, 470))
    d.arrow((1105, 450), (1138, 450), (1138, 395), (1170, 395))
    d.arrow((1105, 490), (1138, 490), (1138, 555), (1170, 555))
    d.text(55, 637, "Tested on 16 sample passages: correct passage in the top 4 for 24 of 25 questions; "
                    "7 of 8 unrelated questions rejected.", 13.5, MUTED)
    d.save("3-knowledge-retrieval.svg")


def qualification() -> None:
    d = Drawing(1400, 720, "Lead qualification and sentiment",
                "The model reports what was said. Fixed rules decide the score.")
    chain = [("Caller says", ["“I am the owner,", "budget ₹2,000 a month”"], "browser"),
             ("Gemini extracts", ["Facts with quoted", "words, plus sentiment"], "ai"),
             ("Evidence check", ["Quote must appear in", "the caller's words"], "agent"),
             ("Merge", ["Add to what is", "already known"], "agent"),
             ("Score", ["Fixed rules,", "out of 100"], "agent")]
    for i, (title, lines, kind) in enumerate(chain):
        x = 55 + 268 * i
        d.box(x, 105, 220, 100, title, lines, kind)
        d.step(x + 4, 109, i + 1)
        if i < 4:
            d.arrow((x + 220, 155), (x + 268, 155))

    d.group(30, 245, 900, 350, "How the points are given", "agent")
    rows = [("Need", 30, "Specific problem 30 · general interest 15"),
            ("Budget", 25, "Covers a plan 25 · no amount 10 · too low 5"),
            ("Authority", 20, "Decides or influences 20 · not involved 5"),
            ("Timeline", 25, "Within 3 months 25 · 3–6 months 15 · later 5")]
    for i, (name, points, rule) in enumerate(rows):
        y = 295 + 72 * i
        d.text(60, y + 19, name, 15, weight=650)
        d.text(150, y + 19, f"{points} points", 13, MUTED)
        d.shapes.append(f'<rect x="250" y="{y + 6}" width="{points * 20}" height="16" rx="4" fill="#257de0"/>')
        d.text(250, y + 46, rule, 12.5, MUTED)
    d.text(60, 578, "An unknown fact scores 0.", 12.5, MUTED)

    d.box(1000, 255, 360, 65, "Hot · 70 or more", ["Sales should follow up first"], "good")
    d.box(1000, 335, 360, 65, "Warm · 40 to 69", ["Interested, details missing"], "api")
    d.box(1000, 415, 360, 65, "Cold · below 40", ["Little sign of a purchase"], "data")
    d.box(1000, 515, 360, 80, "Sentiment, shown separately",
          ["Two negative turns in a row", "flag the call for a person"], "bad")
    d.arrow((1237, 205), (1237, 228), (975, 228), (975, 287), (1000, 287))
    d.arrow((975, 287), (975, 367), (1000, 367))
    d.arrow((975, 367), (975, 447), (1000, 447))

    d.box(55, 625, 620, 65, "Saved to leads.db", ["Sensitive numbers and email addresses redacted"], "data")
    d.box(725, 625, 635, 65, "Used immediately", ["Lead panel updates; the agent asks for one missing fact"], "agent")
    d.save("4-lead-qualification.svg")


if __name__ == "__main__":
    for draw in (overview, conversation, retrieval, qualification):
        draw()
    print("diagrams written to", OUT)
