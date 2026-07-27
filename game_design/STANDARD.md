# Designer Output Standard

Designer generates one complete `game_design` JSON per run. Controller treats it as a read-only world blueprint.

## Hard Requirements

1. The story covers Grade 10 first semester plus winter vacation: September to January, five months total.
2. `turn_policy.total_turns` is decided by Designer from narrative density, school rhythm, relationship arcs, measurement coverage, and bridge-scene needs.
3. `timeline.length` must equal `turn_policy.total_turns`.
4. Total turns must be 120-150, because MSSMHS has 60 items and the game needs enough plot/bridge turns between measurement candidates.
5. Each timeline entry must declare `narrative_role`: `plot`, `bridge`, or `measurement_candidate`.
6. `plot` and `bridge` turns should not carry questionnaire targets. They exist for pacing, transitions, consequences, daily texture, and relationship continuity.
7. `measurement_candidate` turns may carry 1-2 `questionnaire_targets`; Controller still decides whether the generated question is truly a test point.
8. All 60 original questionnaire items must be covered across the whole design as candidates.
9. Month and time order must be semantically increasing. Do not force a fixed "early/middle/late month" template.
10. Events must stay realistic, restrained, and campus-daily. No fantasy, conspiracy, extreme violence, diagnosis, or complete cure/change arcs.

## Recommended Rhythm

- `measurement_candidate`: about 45%-60% of turns.
- `plot` + `bridge`: about 40%-55% of turns.
- The first few turns should prioritize environment, people, and situation before measurement.
- Between two measurement-heavy turns, use bridge turns for reaction, aftermath, transition, small talk, family contact, class routine, or quiet self-management.
