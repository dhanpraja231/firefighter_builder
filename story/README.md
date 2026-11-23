# Story

The story for the Track 1 film. SPEC.md section 2 has the scenario file format. This page covers what happens and who is in it.

## Premise

It's night in a 3-floor apartment block, and a kitchen fire starts on floor 3. No human firefighters go inside.
Three robots and an AI commander are sent in to get everyone out. The agents decide how the night plays out, so each run
ends differently. When a run ends, a human reviews the outcome and approves or declines it.

## Style

Documentary, made to feel like an incident replay:

- bodycam shots from the robots and overhead shots from the scout drone
- captions with timestamps, agent names, and what each agent decided and why
- radio-style call-outs between the robots and the commander
- no music-video drama: the tension comes from the decisions

## Setting

- 3-floor apartment block, at night.
- The fire starts in a kitchen on floor 3 and spreads over time.
- One main stairwell, which can collapse (see Twists).
- Apartments behind closed doors, a hallway on each floor, one exit at ground level.

## Robots

All the robots and the commander share the same calm, professional, procedural voice. What differs is their job, not
their personality.

| Agent | Job |
| --- | --- |
| Commander (AI) | Assigns floors and tasks, sets priorities, re-plans after twists |
| Scout drone | Sweeps floors, finds victims and hot spots, reports back |
| Hose robot | Fights the fire and keeps the stairwell and hallways passable |
| Rescue robot | Reaches victims, talks them into leaving, guides or carries them out |

## Victims

There are 6 units, 8 people in all. Pairs are separate agents with their own memory, but they start together and try to stay together.

| Unit | Character | What makes the rescue hard |
| --- | --- | --- |
| Elderly resident | Stubborn and polite. Has lived there for decades. | Won't leave without their pet |
| Parent and child | The parent is panicked. The child is young and scared. | The parent runs the wrong way, and the child can go missing |
| Skeptic | Distrusts robots and wants a human firefighter | Refuses help from a machine and argues with it |
| Teen | Filming everything on their phone | Won't leave because they're streaming the fire live |
| Regular resident | Ordinary, cooperative | None. They follow instructions, which makes them the baseline to compare the others against. |
| Couple | An ordinary couple | Want to stay together, and splitting them up slows the rescue |

Each victim remembers what they have seen and what the robots told them, and reacts to it on the next tick.

## Twists

The Director agent decides at runtime which twists fire, and when, from the seed and the state of the run.

- **Stairwell collapse:** the stairwell gives way while robots are on the upper floors, cutting off the main route.
  The robots have to find another way or decide who goes first.
- **Child goes missing:** after the parent and child are found, the child slips away before they reach the exit. The
  parent panics, and a robot has to be pulled off another task to search.

## Beats

The film runs about 2 minutes.

1. **Alarm.** The fire starts on floor 3. The robots arrive and the commander assigns floors.
2. **Sweep.** The scout searches floors 2 and 3 and finds the victims. Each one reacts in character.
3. **Rescues.** The robots start getting people out. The elderly resident won't leave, the skeptic argues, and the teen keeps filming.
4. **Twist.** The Director triggers the stairwell collapse, the child going missing, or both.
5. **Re-plan.** The commander re-assigns the robots. Some victims get out, and some may not.
6. **End card.** It shows who was saved, the key decisions and the reasons for them, and the human's verdict on the outcome.

## Ending

Open. The agents decide, so a run can end with everyone saved, some saved or no one saved. A human approves or declines
the overall outcome of each run. That verdict will later feed a self-improvement loop, so future runs can do better
(not built yet).

## Open questions

- Do the robots also ask the human before individual risky actions (breaching a door, entering a collapsing floor),
  or does the human only judge the final outcome?
- Names for the victims.
- Which pet the elderly resident has.
