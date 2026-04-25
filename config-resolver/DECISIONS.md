# DECISIONS

This file explains the main decisions I made for the configuration handling in this project.

---

## Supported and Excluded Configuration Sources

**Supported:**
- **Environment variables**
  I decided to support environment variables because they are a very common way of passing configuration, and they are easy to use in most environments.

- **Profiles**
  I also added the ability to use profiles, because this makes it flexible for users who want to organize different sets of configuration, and it is easy to extend with more profiles if needed.

**Excluded:**
- **Dry-run**
  I did not add a dry-run feature.
  - My code is designed more as a library and not as a tool for running tasks, so there is no real "operation" that needs to be previewed.
  - Without a fixed task-running flow, a dry-run doesn't make sense here.

- **Diff of changes**
  I skipped showing a diff of what would change.
  - Because everything is happening in code and not as an automated job, there is no clear "before and after" state to compare.
  - Users can still see conflicts, which I think covers the most important part.

---

## Precedence Rules

- **Environment variables always take precedence**
  - If a value is set as an environment variable, it will always be used first.
  - This is why I based my code on pydantic-settings, which supports this idea very well.

- **Profiles processed by last update**
  - After environment variables, I look at each profile and for every setting, I take the value from the profile which was updated last.
  - Values are resolved field by field, not all at once for each profile.

- **Alternatives considered**
  - I thought about using a priority order or merging values differently, but my chosen method is clearer, predictable, and easier for others to follow or change.

---

## Definition of Conflict

- **What is a conflict?**
  - A conflict happens when the same setting is set with different values from two sources (for example, both environment variable and API config).

- **Example of a conflict:**
  - If `DATABASE_URL` is set as an environment variable **and** also set by an API config, that is a conflict.
  - In this case, the environment variable wins.

- **Example of not a conflict:**
  - If `DATABASE_URL` exists in two different profiles, but one of them is set to `None`, I simply use the profile that actually has a value.
  - This is not a conflict because there is only one real value.

---

## Handling Source Failures

- **How source failures are handled:**
  - If any configuration source fails (for example, can’t be loaded or has an error), I skip it and show a warning to the user.
  - I chose this approach to make the core logic simple and robust, so a small failure does not break everything.

- **Custom handling is possible:**
  - It’s possible to extend the BaseConfig class and implement stricter or custom error handling if a user wants to do that.

---

## Skipped or Simplified Features & What I Would Improve

- **What I simplified or left out:**
  - I did not add complex logic for failure handling.
  - I only focused on the main part: resolving config, without making a CLI tool or full package.

- **What I would improve with 10 more hours:**
  - The first thing would be to make a CLI tool so users can interact with the configuration easier.
  - If I had some time left, maybe I would add async support so the config code could be used in async apps.
  - But I think most of the time would go on the CLI, as that would help people try the tool faster.

---
