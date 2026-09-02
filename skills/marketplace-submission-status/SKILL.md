---
name: "marketplace-submission-status"
description: "Check a GitHub marketplace submission issue and distinguish automated validation from final listing approval."
---

# Marketplace Submission Status

Use this procedure when checking the status of a plugin or repository submitted through a GitHub issue.

1. Retrieve the submission issue’s current state, labels, URL, and comments. Confirm all four fields are available or mark the missing field unknown.
2. Identify automated validation comments and record each explicit result, including the validated commit when shown. Confirm every reported check is supported by comment text.
3. Separate readiness signals from final approval. Treat validation, compatibility, security-baseline, or “ready for review” messages as automated gates unless the issue explicitly records listing approval or publication. Confirm the status wording names the remaining review stage.
4. Check for direct evidence of completion, such as an explicit approval, publication notice, or closed issue with a stated successful outcome. Confirm completion only when that evidence exists; otherwise report the submission as pending.
5. Return the issue link, concise passed checks, and the next outstanding stage. Confirm the summary does not present an automated security baseline as a security audit or human endorsement.
