# Correct generated defeasible expectations

## Goal

Regenerate the 701 published DeLP expectations from García and Simari’s definitions so Gunray can check complete results against an independent reference.

## State

The reference and regenerated corpus preserve the original case IDs and input theories. An independent comparison found 57 changed result sets and agreement with the repaired Gunray on all 701 inputs. The corpus replay and two focused paper examples passed locally.

## Decisions and why

- Use exhaustive support subsets, nontrivial activation subsets, and acceptable argumentation lines to implement Definitions 2.5, 3.1–3.5, 4.1–4.7 and 5.1–5.3. Reuse the companion repository’s own positive grounding functions. This reference has no Gunray dependency. [García and Simari](https://doi.org/10.1017/S1471068403001674)
- Keep the original stimulus cohort and report complete rows for facts and grounded source heads. `--refresh-existing` regenerates that cohort without resampling the inputs or renumbering cases.
- Record the new expectation producer in the generated files. The DePYsible adapter still owns unrelated live and harvested cases.
- Generate the YAML with the same CRLF line endings as the retained corpus so unchanged theories do not appear as changes in the diff.

## Surprises

The old `defeasible_gen_strict_override_0001` result warrants both `goal` and its strict complement. DePYsible builds structures from derivations and marks them without checking whether the support contradicts Π. Stability across hash seeds could not detect that violation of García and Simari’s Definition 3.1(2).

## Next step

Publish and merge the companion PR after verifying the regenerated cases. Update the immutable corpus pin in Gunray #3 and run its full hosted suite.
