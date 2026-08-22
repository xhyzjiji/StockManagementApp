# Rule: <Topic Name>

One short sentence describing the durable topic area this Rule file owns. Keep it broad enough for future rules in the same topic.

Owner: <owner>

## Context

Optional section. Include it only when facts are required to apply the rules below. Keep this section short and write it in plain language. There is no fixed format. If included in a real Rule file, use the heading `## Context`.

<Briefly explain the source of truth, protected files, lifecycle state, ownership boundary, frozen concept, or other facts the agent must know before applying these rules.>

## <Scenario Name>

WHEN <trigger condition>:
- MUST <required behavior>.
- MUST <required behavior with a clear boundary or exception>.
- MUST read `<doc-name>.md` before editing code covered by this scenario.
- MUST NOT <forbidden behavior>.
- MUST NOT <forbidden behavior unless explicit exception>.
- MUST invoke `<skill-name>` when the change requires step-by-step operational guidance that does not belong in this Rule file.

## <Another Scenario Name>

WHEN <trigger condition>:
- MUST <required behavior>.
- MUST NOT <forbidden behavior>.

## Related Docs

Optional section. Include it only when focused reference docs are required by `MUST read` bullets above. Do not list broad background reading. If included in a real Rule file, use the heading `## Related Docs`.

- `<doc-name>.md`: <when to read it>

## Related Skills

Optional section. Include it only when an existing or newly created Skill provides the detailed workflow behind a short global Rule trigger. Do not paste the full workflow into this Rule file. If included in a real Rule file, use the heading `## Related Skills`.

- `<skill-name>`: <when to invoke it>
