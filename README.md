# Introduction

In embedded code of sufficient criticality, dead code is forbidden.

But how do you detect it? How can you see whether your final binary
includes functions that no-one calls?

It is easy to gather the complete list of functions in a binary - you use
your platform's `objdump`, to do something like this...

    sparc-rtems-objdump -t ${TARGET} \
        | grep "F .text" \
        | awk '{print $NF}' \
        | sort -u \
        > all_functions.log

Now, if you were able to collect a list of *actually used* functions,
you could subtract the two - via GNU `comm`:


    comm -2 -3 all_functions.log used_functions

...but how to collect these "used_functions"?

# Usage

Simple: modify your Makefiles to spawn your cross-compiler with `-E`
instead of `-c`. This will give you a nice set of `*.o` files that
aren't really object files - they are instead preprocessed, standalone
source.

Now "feed" this standalone preprocessed source to my script here:

    cd /path/to/preprocessed
    rename -E 's,o$,c,' *.o
    cd -
    ./detect_used_functions.py /path/to/preprocessed/*.c

...and you'll get the sorted list of actually used functions; 
wherever they may appear:

- In call sites
- Used as function pointers in right-handside assignment
- Used as function pointers in global arrays
- etc

Is this script bulletproof? Can you trust it with your life?

I don't know - I did my best to get there. Please raise an issue in this
Github repo if you see that I missed something.

--

Made during the COVID-19 quarantine days of 2020. The silver lining is
that at least this isolation allows for some focused, uninterrupted work.

Thanassis Tsiodras ( ttsiodras@gmail.com )
