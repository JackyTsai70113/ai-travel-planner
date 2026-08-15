# Sustainable Iteration and Learning

## Iteration metrics

Measure outcomes rather than agent activity:

- Escaped defects.
- Review findings that were valid.
- Rework cycles.
- Acceptance criteria without evidence.
- Human interventions and why they occurred.
- Lead time and agent compute cost.
- Flaky or non-deterministic validations.
- Contract and documentation drift.

Do not optimize for number of agents, number of tool calls, or autonomous time.

## Retrospective questions

1. Which assumptions were wrong?
2. Which gate caught the highest-value problem?
3. Which gate added cost without useful signal?
4. Did role or permission boundaries fail?
5. Did a platform impact appear too late?
6. Which lesson is supported by repeatable evidence?
7. What should remain a local exception rather than become global policy?

## Policy promotion

A candidate lesson becomes policy only when:

- It has evidence from one high-severity failure or multiple ordinary runs.
- Its scope and exceptions are documented.
- It can be validated or reviewed.
- It does not grant broader autonomy.
- Migration and rollback are clear.
