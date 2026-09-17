# Video walkthrough script

Target: 1:45–2:00. Screen recording, voiceover. Each line is roughly what fits
in the time next to it — read it once at a natural pace before recording to
check the fit, and trim rather than rush.

---

**[0:00–0:15] The gap — no screen share yet, or a static title card]**

> "SaaSquatch is built for volume: scrape, enrich, export. Enrichment costs a
> credit, so you pay to enrich a lead before you know if it's any good, and a
> 400-row CSV isn't a pipeline — nobody can act on 400 leads this week. I
> built the layer that sits between scraped and contacted."

**[0:15–0:30] Setup screen]**

> "You start by saying what you're actually trying to do. SaaSquatch's own
> site reports 2,000-plus sales teams and 30-plus searchers using it today —
> two groups it doesn't distinguish between: sales teams looking for
> customers, and searchers — including Caprae's own deal team — looking for
> businesses to buy. Same data, opposite criteria."

*(click "Businesses to buy," show the profile dropdown, upload the seed CSV)*

**[0:30–0:50] Upload → scoring in progress → triage view]**

> "Drop in a CSV — any export works, columns get auto-matched. 322 rows,
> real-world messy: five different ways to write revenue, 22 duplicate
> companies spelled differently. Dedup and validation run first, then a
> signal scan of each company's site — one polite request, robots.txt
> respected — and then scoring."

*(let the progress bar finish, land on the triage queue)*

**[0:50–1:15] The score explanation — this is the core of the pitch]**

> "Here's the one where I want to slow down. This is a 20-year-old HVAC
> company. In buy mode it's an 88 — top of the list. Why: owner-operated,
> right size, and *no analytics, no online booking, nothing modernized.*
> That last one is worth pointing out — a neglected website is normally a bad
> sign. Here it's the opportunity: a good business nobody's added technology
> to yet, which is exactly Caprae's thesis."

*(click the same company, flip the mode toggle to "sell")*

> "Flip to sell mode, same company: 41. Same signals, opposite verdict —
> because a sales rep can't sell software to a company with no digital
> presence. Same data, same scanner, two answers, because the criteria
> actually differ."

**[1:15–1:35] Triage + the credit argument]**

> "Review happens on the keyboard — J and K move, A accepts, X rejects — so
> going through fifty leads doesn't mean fifty clicks. And this quadrant here
> is the part I think matters most commercially: it splits score from
> confidence. High score, low confidence is a specific, short list — that's
> exactly which leads are worth spending an enrichment credit on. This
> doesn't compete with SaaSquatch's credit model, it makes it more efficient."

**[1:35–1:50] Close]**

> "Everything here is deterministic — same input, same score, every time —
> because a number a reviewer can't reproduce isn't one they can trust. Full
> architecture, test suite, and the seed dataset are in the repo. Thanks for
> watching."

---

## Filming notes

- Record the browser at 1280×800 or similar — the queue and detail panel both
  need to be legible without heavy zooming.
- Have the seed CSV (`backend/app/data/seed_leads.csv`) already downloaded
  and ready to drag in — don't burn time finding the file on camera.
- Pick the sell/buy comparison company *before* recording: run the dataset
  once, find a lead that scores high in Buy and noticeably lower in Sell (an
  old, small, neglected-site company usually does), and note its name so you
  don't hunt for it live.
- If the rescore-without-refetch feature fits in time, it's the single best
  addition: drag a weight slider, hit rescore, and point out the queue
  reorders instantly with no network calls — proof the architecture is real,
  not a demo trick.
- Keep the voiceover close to the word count above — reading it verbatim
  should land close to 1:50.
