# Common PSS Workflows

## Workflow 1: First-Time PSS Setup

**Scenario**: You just installed PSS and want to verify it works.

**Steps:**

1. **Check initial status**
   ```
   /pss-status
   ```

   Expected: "Index file missing" or old index

2. **Build the index**
   ```
   /pss-reindex-skills
   ```

   Wait for completion (1-2 minutes)

3. **Verify success**
   ```
   /pss-status
   ```

   Expected: "Index Status: Exists", recent timestamp

4. **Test with a prompt**
   ```
   "I need to write Python unit tests"
   ```

   Expected: PSS suggests relevant testing skills with HIGH confidence

**If any step fails**: See [pss-commands.md](pss-commands.md) section 5.0 Troubleshooting common PSS issues -- covers 5.1 PSS commands not found or not responding, 5.2 Empty or missing skill suggestions.

## Workflow 2: Adding New Skills

**Scenario**: You installed new skills from a marketplace.

**Steps:**

1. **Install skills** (via marketplace or manual installation)
   ```
   /plugin install new-skill-pack
   ```

2. **Reindex immediately**
   ```
   /pss-reindex-skills
   ```

   Why: PSS does not auto-detect new skills

3. **Verify new skills indexed**
   ```
   /pss-status
   ```

   Check: "Total Skills Indexed" should increase

4. **Test suggestion**
   Create a prompt using keywords from the new skills

   Expected: New skills appear in PSS suggestions

## Workflow 3: Debugging Missing Suggestions

**Scenario**: PSS should suggest a skill but does not.

**Steps:**

1. **Check PSS is working**
   ```
   /pss-status
   ```

   Verify: "Index Status: Exists", no errors

2. **Reindex to refresh**
   ```
   /pss-reindex-skills
   ```

3. **Check skill metadata**
   - Open the skill's SKILL.md
   - Verify frontmatter has `keywords` and `categories`
   - Check if your prompt keywords match skill keywords

4. **Try explicit keywords**
   Rephrase your prompt to use exact keywords from skill frontmatter

   Example: If skill has `keywords: ["pytest", "unittest"]`, try:
   ```
   "Write pytest tests for the API"
   ```

5. **Check skill is available to agent**
   - PSS only suggests skills the current agent can use
   - Review agent's frontmatter `available_skills` list
   - If skill missing, add it to agent's skill list

For detailed troubleshooting, see [pss-commands.md](pss-commands.md) -- 5.2 Empty or missing skill suggestions and 5.3 Index file errors or corruption.
