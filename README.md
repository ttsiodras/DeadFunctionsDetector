In embedded code of sufficient criticality, dead code is forbidden.

How can one detect it, then?

# Take 1

Well, if you ask a mathematician "how do I detect dead code", he will answer:

  *"You can't. It's equivalent to the halting problem."*

The reason he will say that, is because this code...

    int main()
    {
        function_that_will_run_forever();
        FOO();
        BAR();
    }

...will actually never call functions `FOO` and `BAR`, since it will get stuck
at the first statement.

And detecting whether a program halts or not, is an undecideable problem;
no tool made by man can decide it.

So... forget about it.

# Take 2

I am no mathematician. Like all engineers, I learned pretty quickly that
the perfect is the enemy of the good - and that in the real world,
"close enough" is, very frequently, good enough.

**There are two categories of dead code:**

- One is about *sections of code inside functions* that are impossible
  to exercise; for example bodies of “if” whose decisions can be *proven*
  to always evaluate one way. A good Static Analyser can frequently see
  that e.g. a specific "if"'s condition will always be true - making the
  corresponding "else"'s body 'dead code'. It can also warn about a large
  subset of the mathematician's infinite loops.

- Then, another category is the functions themselves; i.e. *functions
  defined but not used or called by anyone*.

- The rest of the functions - like FOO and BAR in the pathological example
  above - I will *consciously choose to pretend they only exist in the
  heads of mathematicians*.

# Unreferenced functions

Assuming I have access to a static analyser and cover the first category,
what do I do about the second one? How can I see whether the final binary
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

# Naive scripting

Something that many people - including me - consider initially as an easy
solution to this problem, is to scan the disassembled binary to find
all calls; and collect in a list all called symbols.

Voila!

Sadly, that will only partly work. There's a lot of code that uses
function pointers; e.g. implementing state machines via 2D arrays
indexed by state and incoming event, and "jumping" to the related action
via the stored function pointer.

Scanning the disassembled output for this, will just show a cryptic...

    call %someregister

...with the register getting the value by the previous code, that
indexes in the table.

We somehow need to deal with indirect calls - calls made via function
pointers.

**And this is what this script does**. It deals with both
normal and indirect calls, gathering all references to our functions;
and only reporting the functions in our binary that are not referenced
anywhere.

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
script, alongside the ELF binary - e.g. with an invocation like this:

    ./detect_unused_functions.py the_elf_binary /path/to/preprocessed/*.c

The script will record the dead functions in an output file called
`deadFunctions`,

The functions actually used are collected from everywhere...

- all call sites
- function pointers in right-handside assignments
- function pointers in global arrays
- etc

# How does it work?

As follows:

- It uses objdump to collect all functions' names from the ELF.
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
