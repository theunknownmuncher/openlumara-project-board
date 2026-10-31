## 1. Long and short

- [ ] 1.1 Short one.
- [ ] 1.2 In `src/core/command-generation/adapters/devin.ts`, add the Devin adapter so that `.devin/workflows/opsx-<id>.md` files are written with frontmatter `name`, `description`, `category` and `tags` produced by the shared helpers in `command-generation/yaml.ts`, keeping the adapter a pure formatter that never touches the filesystem itself, and make sure the golden tests under `test/command-generation/__fixtures__/devin/` cover an empty skill list, a skill with no arguments and one whose body already references `/opsx:` commands, because that is where the previous adapter silently dropped the suffix.
- [x] 1.3 Document the adapter in the supported-tools matrix.
