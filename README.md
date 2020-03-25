# Introduction

In embedded code of sufficient criticality, dead code is forbidden.

There are two categories of dead code:

- One is about *sections of code inside functions* that are impossible
  to exercise; for example bodies of “if” whose decisions can be *proven*
  to always evaluate one way. A Static Analyser can see that e.g.
  a specific "if"'s condition will always be true - making the
  corresponding "else"'s body 'dead code'. Use a static analyser - e.g. the
  [Clang Static Analyser](https://clang-analyzer.llvm.org/), which is
  available under a free, open-source license - to detect these
  cases.

- Then, the other category is about the functions themselves; i.e. *functions
  defined but not used by anyone*. 

How does one detect those? How can one see whether the final binary
includes functions that no-one calls?

It is easy to gather the complete list of functions in a binary - via the
platform's `objdump`, and something like this...

    sparc-rtems-objdump -t ${TARGET} \
        | grep "F  *\.text" \
        | awk '{print $NF}' \
        | sort -u \
        > all_functions

Now, if we were able to collect a list of *actually used* functions,
we could subtract the two - via GNU `comm`:

    comm -2 -3 all_functions used_functions

...but how to collect these "used_functions"?

That's what this script does.

# Usage

Modify your Makefiles to spawn your cross-compiler with `-E`
instead of `-c`. This will give you a set of `*.o` files that
aren't really object files - they are instead preprocessed,
standalone source code.

Rename them appropriately:

    cd /path/to/preprocessed
    rename -E 's,o$,c,' *.o
    cd -

...and then "feed" these standalone preprocessed sources to this
script - e.g. like this:

    ./detect_used_functions.py the_elf_binary /path/to/preprocessed/*.c

The script will record the dead functions in an output file called
`deadFunctions`,

The functions actually used are collected from everywhere...

- all call sites
- function pointers in right-handside assignments
- function pointers in global arrays
- etc

How it works:

- uses objdump to collect all functions' names from the ELF.
- It then uses Python Clang bindings to parse the provided C code.
- The parsed ASTs are stored in a “.cache” folder, to avoid reprocessing
  in subsequent invocations.
- The entire AST is then traversed - and every token of every expression
  is checked, to see if it refers to one of the already recognized
  *(in the first step)* functions. If so, the function is marked as "used".
- This addresses all mentions of functions in the C code we compile.
  But this still doesn't suffice - because if one of the C files
  calls a function we don't have the source code of (e.g. `ep_FOO`)
  and this function in turn calls `ep_BAR`, then `ep_BAR` is *not*
  a dead function - even though it doesn't appear anywhere in any
  of the C sources.
- So we will also collect the "mentions" made in the disassembly,
  and mark them as "used", too.
- Finally, the set of "used" is subtracted from the set of "all" - and
  whatever remains is stored inside the `deadFunctions` output.

--

Made during the COVID-19 quarantine days of 2020. The silver lining with
this isolation is that it allows for some focused, uninterrupted work.

Thanassis Tsiodras ( ttsiodras@gmail.com )
