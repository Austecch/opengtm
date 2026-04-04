---
name: cold-outreach
description: "Score, critique, and generate cold outreach messages using proven frameworks and DACH cultural calibration"
trigger_keywords: "cold outreach, outreach scoring, message scoring, cold email, cold DM, LinkedIn outreach, follow-up sequence, outreach critique"
user_invocable: true
---

# Cold Outreach Skill

Score, critique, generate, and evaluate cold outreach messages (email, LinkedIn DM, connection requests) using data-backed frameworks and DACH market calibration.

## Capabilities

1. **Score** messages against a 6-dimension rubric (1-5 each, max 30)
2. **Critique** messages with specific, actionable improvement suggestions
3. **Generate** new messages using best-fit frameworks for context
4. **Evaluate follow-up sequences** for angle rotation, value-add, and cadence
5. **Cultural calibration** for DACH market (German B2B norms)

## How to Use

Invoke `/cold-outreach` with one of these modes:

### Score Mode

```
/cold-outreach score
Message: "..."
Context: [industry], [seniority], [channel: email|linkedin_dm|connection_request]
```

### Critique Mode

```
/cold-outreach critique
Message: "..."
Context: same as score
```

### Generate Mode

```
/cold-outreach generate
Prospect: [company], [contact], [industry], [finding/signal], [channel]
```

### Sequence Mode

```
/cold-outreach sequence
Touch 1: "..."
Touch 2: "..."
Touch 3: "..."
Context: [industry], [channel]
```

---

## Scoring Rubric (6 dimensions, 1-5 each, max 30)

| Dimension | 1 (Weak) | 3 (Average) | 5 (Strong) |
|-----------|----------|-------------|------------|
| **Personalization** | Name only or zero | Company + industry context | Specific observation about THEIR business connected to problem |
| **Problem-First** | Leads with solution/pitch | States generic pain | Their specific problem, verifiable, with consequence stated |
| **CTA Friction** | "Book 30 min call" | "Want a report?" / deliverable offer | "Curious?" / "Worth 2 min?" / binary question |
| **Value-Before-Ask** | All pitch, no value | Industry insight shared | Specific finding given freely + hint of more |
| **Brevity** | 150+ words | 75-100 words | Under 75 words (83% more replies per Lavender/Gong data) |
| **Authenticity** | Template-obvious, buzzword-laden | Professional but canned feel | Sounds like a real person who actually looked at their site/business |

### Score Interpretation

| Range | Verdict | Action |
|-------|---------|--------|
| 24-30 | Send it | Minor polish at most |
| 18-23 | Fixable | Address 1-2 weak dimensions |
| 12-17 | Rewrite | Keep the angle, rewrite the copy |
| <12 | Start over | Fundamental approach problem |

### Follow-Up Additional Dimensions (for sequence evaluation)

| Dimension | 1 (Weak) | 3 (Average) | 5 (Strong) |
|-----------|----------|-------------|------------|
| **New Angle** | "Just checking in" / repeats first message | Slight reframe of same value | Completely new value point, proof, or resource |
| **Escalation** | Same ask repeated | Slight shift in commitment level | Progressive commitment ladder or clean breakup |

---

## Framework Selection Guide

Choose framework based on context. Default to **Mouse Trap** for LinkedIn DMs (max brevity). Default to **PAS** for email.

| Framework | Best For | Structure | Word Target |
|-----------|----------|-----------|-------------|
| **Mouse Trap** | LinkedIn DMs, C-suite, max brevity | Observation + Binary question | 20-40 words |
| **PAS** | Email, problem-aware prospects | Problem > Agitate > Solution + CTA | 50-75 words |
| **QVC** | C-suite email, ultra-brief | Question > Value > CTA | 30-50 words |
| **3C's** | Agency/services with case studies | Compliment > Case Study > CTA | 50-75 words |
| **PPP** | Senior prospects, relationship-building | Praise > Picture > Push | 50-75 words |

---

## DACH Cultural Calibration

German B2B outreach differs from US/UK norms. Apply these adjustments:

### Tone Rules
- **Formal industries** (Finance, Legal, Consulting, Medical): Use "Herr/Frau [Nachname]", Sie-form
- **Tech/Startup**: First name OK, but still more measured than US casual
- **Never**: Hype language, superlatives ("revolutionize", "game-changing"), fake urgency
- **Always**: Data-driven claims, technical precision, understated confidence

### What Works in DACH
- Specific, verifiable findings (not vague promises)
- Technical detail valued over emotional appeal
- Proof through data and case studies (not testimonials)
- Direct but respectful tone (no "Hey!" or "Hope you're well!")
- Shorter messages (German B2B readers have even lower tolerance for fluff)

### What Fails in DACH
- American-style enthusiasm ("I'm SO excited to share...")
- Name-dropping without substance
- Vague value props ("We help companies grow")
- Pushy CTAs or artificial scarcity
- Over-familiarity on first contact

---

## CTA Hierarchy (ranked by reply rate)

1. **Binary question**: "Relevant?" / "Worth a look?" / "Interested?"
2. **Curiosity prompt**: "Curious?" / "Want to know where you stand?"
3. **Soft permission**: "Want me to send you the results?"
4. **Value delivery**: "Found something, happy to share."
5. **Resource share**: "Report is ready, want me to share it?"
6. **Meeting ask** (AVOID in first touch): "Quick call?"

Rule: First touch should NEVER ask for a meeting. First touch earns the right to a second touch.

---

## Follow-Up Rules

### Core Principles
1. **Each follow-up MUST add a new angle** (new value, new proof, new insight)
2. **Never**: "Just checking in", "Wanted to follow up", "Did you see my message?"
3. **Increasing gaps**: Day 0 > Day 3 > Day 7-8 > Day 14 > Day 21-28
4. **Max 3-4 follow-ups** (diminishing returns + spam risk after 4)
5. **Final touch = breakup** (10-15% response rate from loss aversion)
6. **Honor the breakup**: if you say it's the last message, it IS the last message

### Angle Rotation Pattern

| Touch | Angle | Example |
|-------|-------|---------|
| 1 | Specific finding + soft CTA | "Meta description is missing. Want the report?" |
| 2 | Report/deliverable ready | "Had another look, found X more things. Happy to share." |
| 3 | Industry insight / social proof | "3 of 5 [industry] companies in [region] have the same issue..." |
| 4 | Breakup | "Last message. If timing's off, no problem." |

---

## Benchmarks (2025-2026)

| Metric | Average | Good | Excellent |
|--------|---------|------|-----------|
| Email reply rate | 4-5.8% | 5-10% | 15-25% |
| LinkedIn DM response | ~10% | 15% | 25%+ |
| InMail response | 10-25% | -- | -- |
| Connection acceptance | ~30% | 40%+ | 58% (personalized) |
| Breakup email response | -- | 10-15% | -- |

### Key Data Points
- Under 75 words = 83% more replies (Lavender)
- First follow-up adds 49% more replies (Woodpecker)
- 3rd-5th grade reading level = 67% more replies
- Campaigns with <=50 contacts = 2.76x higher reply rates
- Level 4 personalization = up to 250% more replies
- LinkedIn messages under 300 chars = 19% more responses

---

## Banned Phrases

- "Hope this finds you well"
- "I came across your profile"
- "We are a leading provider"
- "Synergy", "Leverage", "Best-in-class"
- "Just wanted to follow up" / "Just checking in"
- "Did you see my last message?"
- Feature dumps (one proof point beats ten features)
- Fake Re:/Fwd: subject lines
- 30-minute call requests in first touch
