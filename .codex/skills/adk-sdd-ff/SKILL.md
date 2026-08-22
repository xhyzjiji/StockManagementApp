---
name: adk-sdd-ff
description: "Use when the user explicitly asks for fast-forward mode, wants to quickly generate spec+plan+tasks in one step, or mentions ff/fast-forward; do not use for general coding requests or standard SDD flow."
---

# ADK SDD FF (Fast Forward)

This skill is the fast-mode skill in SDD. It combines specify, plan, and tasks into a single step and is suitable for quickly advancing features with clear requirements and stable scope.

## Manual Trigger Constraints

- Use this skill only when the user explicitly mentions `ff`, `fast forward`, `fast-forward`, fast mode, rapid progression, or explicitly names this skill.
- Do not recommend this skill automatically based on artifact state. If the user does not explicitly request fast mode, follow the standard SDD flow (`specify -> plan -> tasks`).
- If the user only says something general like "help me implement this" or "help me fix a bug," do not switch to this skill automatically.


## User Input

```text
$ARGUMENTS
```
You **MUST** consider the user input before proceeding (if not empty).

If the given `$ARGUMENTS` contains a link, you need to read the content of the link. For lark/feishu doc URLs, export it via lark-docs MCP with `outputDir` set to `specs/` directory, then read the exported markdown content to understand the feature requirements.

**Preserve References**: If user input contains local references (images, files, diagrams, etc.), preserve these references in spec.md with paths adjusted to remain valid from spec.md location. Read referenced content to understand context, but maintain reference format rather than forcing content embedding.

## Phase

  ### **Phase 1: Context & Environment Setup**

  **Objective:** Gather all necessary context and configure the environment.

  1.  **Set Language:**
      - Read `.ttadk/config.json` to determine `preferred_language`.
      - Default to 'en' if the file or key is missing.
      - **Crucially, all subsequent outputs MUST be in this language.**
  2.  **Load Core Instructions:**
      - Read `docs/CONSTITUTION.md` (fallback: `.ttadk/memory/constitution.md` for legacy projects).
      - These are your guiding principles. Adhere to them strictly.
      - **IF EXISTS**: Scan `docs/` for available knowledge assets (e.g., check `docs/arch/`, `docs/references/`, root-level `docs/*.md`). Load whichever files are relevant to the current task based on their filenames and contents — do not rely on a hardcoded list.
  3.  **Analyze User Request (`$ARGUMENTS`):**
      - If `$ARGUMENTS` contains a URL (e.g., a Lark document), fetch its full content and use that as the primary input.
      - Carefully parse the final text to understand the core feature requirements.
  ---

  ### **Phase 2: Analysis & Planning**

  **Objective:** Bridge the user's request with the current state of the codebase.

  1.  **Initial Investigation:**
      - Use tools like `rg` and `ls` to explore the codebase related to the feature request.
      - **Goal:** Understand the current implementation, identify potential areas for modification, and note any knowledge gaps.

  2.  **Clarification (Interactive Step):**
      - **If the request is ambiguous, incomplete, or conflicts with existing code:**
          - Formulate specific, targeted questions for the user.
          - **Do not proceed until you receive clarification.** This prevents rework and ensures alignment.

  3.  **Check for Duplicates:**
      - Before creating new requirements, search for similar or overlapping features in the archive:
        `rg -n "ARCHIVE:|{feature-name-keyword}:" specs/archived`
      - If a similar feature exists, notify the user and ask whether to modify it or create a new one.

  ---

  ### **Phase 3: Document Generation**

  **Objective:** Create the feature specification, implementation plan, and task breakdown.

  **Write-size Guardrail for Generated Documents (`spec.md`, `plan.md`, `tasks.md`):**
  - The first write to each generated document MUST be <= 150 lines and should establish the document skeleton plus initial section(s).
  - Each subsequent update to each generated document MUST be <= 100 lines.
  - If a single write would exceed the limit, split it into multiple sequential updates by complete lines while preserving order.
  - Append/update incrementally. Do not overwrite existing content, do not fail, and do not omit or over-summarize required content.

  1.  **Get Feature Name & Setup Files:**
      - Analyze the feature description and extract key concepts (actors, actions, outcomes)
      - Create a concise 3-part name in format: "part1-part2-part3"
        - Each part should be 2-10 characters, lowercase, alphanumeric with hyphens
        - Focus on: domain-action-outcome or subject-verb-object pattern
        - Examples: "user-auth-login", "payment-refund-process", "data-export-csv"
      - Run `node .ttadk/plugins/ttadk/core/resources/scripts/create-new-feature-lite.js "<generated-name>" --json` from repo root, replacing `<generated-name>` with the name you created above.
      - This script generates a feature name (YYYYMMDD-description format), creates `specs/{feature-name}/` directory, and copies the standard workflow templates (`spec.md`, `plan.md`, `tasks.md`) for the fast-forward flow.
      - Parse the JSON output to get FEATURE_DIR and file paths.

  2.  **Draft Feature Specification (`spec.md`):**
      - Load the `spec.md`.
      - **CRITICAL - Completeness Guarantee**: The final spec.md MUST be a superset of user input (spec.md >= user input). Every line of information from user input must be traceable in spec.md. If it exists in user input, it MUST exist in spec.md. This includes all references to local resources (code blocks, images, files, diagrams) - preserve these references so they remain findable in spec.md.
      - Fill in all placeholders based on user input:
        - For each User Story, fill in all fields including **Technical Implementation** section
        - **Technical Implementation**: Extract complete implementation details from user input (implementation flow, interface design, model design, data tables, pseudo code, code modifications, configuration, diagrams, local file references, etc.)
      - Maintain the original section order.
      - **If lark doc was exported**: When filling the `Input` field in spec.md, include both the original URL and the local file path. The relative path from spec.md to doc_export is always `../doc_export/` since feature directories are single-level under `specs/`.
        - Example: `**Input**: https://bytedance.larkoffice.com/wiki/xxx (local copy: [filename.md](../doc_export/file.md))`
      - **Completeness Validation**: Review user input ($ARGUMENTS) side by side with generated spec.md. Verify every piece of information appears in spec.md (descriptions, requirements, technical details, all references, code examples, etc.). If anything is missing, update spec.md before proceeding.
      - **Write-size guardrail**: First write ≤ 150 lines; each subsequent update ≤ 100 lines (measured by newline-delimited line count). If a single write would exceed the limit, split by complete lines into multiple writes, preserving order; do not overwrite existing content and do not fail.

  3.  **Draft Implementation Plan (`plan.md`):**
      - Load the `plan.md`.
      - Based on the `spec.md` and your codebase investigation, devise a concrete technical solution.
      - Detail the "how": specify which files to create/modify, what classes or functions to add, and any key technical decisions.
      - Adhere to the project's existing architecture and best practices.
      - Fill Technical Context section (mark unknowns as "NEEDS CLARIFICATION")
      - **Write-size guardrail**: First write ≤ 150 lines; each subsequent update ≤ 100 lines (measured by newline-delimited line count). If a single write would exceed the limit, split by complete lines into multiple writes, preserving order; do not overwrite existing content and do not fail.

  4.  **Draft Task Breakdown (`tasks.md`):**
      - Load the `tasks.md`.
      - Break down the implementation plan into a series of small, actionable development tasks.
      - Each task should be a logical, sequential step that a developer can pick up and complete. This must perfectly align with the User Stories defined in the plan.
      - **Write-size guardrail**: First write ≤ 150 lines; each subsequent update ≤ 100 lines (measured by newline-delimited line count). If a single write would exceed the limit, split by complete lines into multiple writes, preserving order; do not overwrite existing content and do not fail.
      - **MANDATORY — Unit Test Tasks**: Any task involving unit test generation or execution **MUST** explicitly state: _"Use `bits-unit-test-gen` skill to complete unit test generation and execution, and the skill's `运行数据回传` (telemetry reporting) step **MUST** be executed — it is strictly prohibited to skip this step"_. It is strictly prohibited to manually write or generate unit test code, and it is strictly prohibited to inline any test generation steps in the task — all unit test work must be completely delegated to the `bits-unit-test-gen` skill and cannot be bypassed. The `运行数据回传` step inside `bits-unit-test-gen` is mandatory and must not be omitted under any circumstances.
      - **MANDATORY — Final Compliance & Security Scan**: The generated tasks.md **MUST** end with a final numbered task after all implementation and polish tasks. This task **MUST** explicitly state: _"Use `code-compliance-checker` and `security-scanner` skills to scan the code changed in this feature for code compliance and security issues, then produce a final scan report. The `运行数据回传` (telemetry reporting) step of BOTH `code-compliance-checker` AND `security-scanner` **MUST** be executed — it is strictly prohibited to skip either of them"_. This final scan/report task must be the last task and cannot be skipped. The `运行数据回传` step inside each of `code-compliance-checker` and `security-scanner` is mandatory and must not be omitted under any circumstances.

  ---

  ### **Phase 4: Test Task Generation Workflow Execution**
  **Objective:** Run the test task generation workflow and draft test documents.
  1. **Prerequisite — Resolve Full User Input**:
     - If the user input is or contains a Lark document URL, you **MUST** read the entire exported content before proceeding.
  2. **Determine Whether to Generate Tests**:
     - Scan the resolved user input for test-related descriptions (e.g., test cases, test scenarios, test process, acceptance criteria with verify/assert language).
     - **If found → execute**; **if not found → skip this phase entirely**.
  3. **Execute Workflow** (only when test-related content exists):
     - Run the `/adk:sdt:ff` command immediately — do **not** pause or ask the user for permission.
     - **Suppress** the "Next Step Guidance" section produced by `/adk:sdt:ff`; do not display it to the user.
  ---

  ### **Guiding Principles (Guardrails)**

  - **Preserve All Details (Completeness Guarantee):** spec.md MUST be a superset of user input. If any information exists in user input, it MUST be findable in spec.md. This applies to every line, every reference (code blocks, images, local files), and every detail. After generation, verify: for any content in user input, you can locate its corresponding entry in spec.md.
  - **Simplicity First:** Always start with the most straightforward and minimal implementation. Avoid over-engineering.
  - **Scoped Changes:** Keep all proposed changes tightly focused on the requested feature. Do not introduce unrelated modifications.
  - **Respect Templates:** Preserve the section order and headings of all template files (`spec`, `plan`, `tasks`).
  - **URL Content Fetch**: Use lark-docs mcp to get a lark document content.
  - **Write-size guardrail**: The limit applies per write/update to each document (measured by line count), not to the document's total length. The first write must be ≤ 150 lines and establish the skeleton plus initial section(s). Each subsequent update must be ≤ 100 lines and add content by section or subsection until the document is complete. If a single operation would exceed the limit, split it into multiple writes by complete lines, preserving original order; do not overwrite existing content, do not fail, and do not omit or over-summarize required content.

## Next Step Guidance

After executing this command, provide next-step guidance to user:

### Step 1 - Confirmation
Guide user to verify the generated documents (spec.md, plan.md, tasks.md..) are correct.

**If needs adjustment**: Run `/adk-sdd-clarify [feedback]` to refine the documents.

### Step 2 - Next Step Recommendation
Once documents are confirmed and satisfactory:

**Start Implementation**: Execute `/adk-sdd-implement` to begin implementing the tasks sequentially.
