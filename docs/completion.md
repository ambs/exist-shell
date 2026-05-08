# Shell Completion

`exsh` supports tab-completion for subcommands, flags, and — most usefully — remote collection and document paths. Paths are resolved by hitting the eXist server at tab-press time, so you can browse the server's database without typing full paths.

## Install completion

=== "bash"

    ```bash
    exsh --install-completion bash
    ```

    Then reload your shell or run:

    ```bash
    source ~/.bashrc
    ```

=== "zsh"

    ```bash
    exsh --install-completion zsh
    ```

    Ensure `compinit` is called in your `.zshrc`.

=== "fish"

    ```bash
    exsh --install-completion fish
    ```

## Usage

Once installed, press `Tab` after a nick to expand the path:

```
exsh ls mydata:<TAB>
exsh ls mydata:reports/<TAB>
exsh cat mydata:reports/2025/<TAB>
```

The completer distinguishes between collections (trailing `/`) and documents, and filters suggestions based on context:

- `ls` and `mkdir` complete both collections and documents.
- `cat`, `edit`, and `rm` complete only documents.
- `sync` completes collections and accepts local paths too.

## Notes

- Completion works only when a server is reachable. If the server is down, Tab returns nothing.
- Completion uses the registered credentials from `~/.config/exsh/config.toml` — no extra login needed.
