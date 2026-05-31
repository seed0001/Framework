# Contacts and Trust Tiers

## Tiers

- **stranger** – Default for new people. Minimal access: knowledge lookup only.
- **friend** – Search, read files, list dirs, knowledge.
- **good_friend** – + system info, processes, build, update_contact.
- **best_friend** – + run_command, write_file, spawn_subagent, DAG, proactive messaging.
- **creator** – Your owner. Full access. Only Creator can change tiers.

## Access

Tool access is enforced automatically. Only Creator can call `update_contact` with `tier=...`. Edit `data/profiles/default/access_policy.json` or `config/access_policy.py` to change what each tier can do.

## Promoting contacts

Use `update_contact(discord_id="...", tier="friend")` to promote someone. Only Creator can do this.
