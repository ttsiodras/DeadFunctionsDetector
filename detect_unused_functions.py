#!/usr/bin/env python3
"""
A utility that parses pre-processed (standalone) C files using Clang,
and then detects and reports all functions inside an ELF that are
not used anywhere.
"""

import re
import os
import sys
import time
import multiprocessing

# For mypy static type checks.
from typing import Set, List, Tuple, Any  # NOQA

from clang.cindex import (
    CursorKind, Index, TranslationUnit, TranslationUnitLoadError)


# For SPARC targets, this is the toolchain prefix
G_PLATFORM_PREFIX = "sparc-rtems-"


def parse_ast(
        t_units: List[Any],
        set_of_all_functions_in_binary: Set[str],
        used_functions: Set[str]) -> None:
    """
    Traverse the AST, gathering all mentions of our functions.
    """

    def process_unit(t_unit: Any):
        result = set()
        # Gather all the references to functions in this C file
        for node in t_unit.cursor.walk_preorder():
            # To find the unused functions, we need to collect all 'mentions'
            # of functions anywhere. This is generally speaking, hard...
            # But... (see below)
            if node.kind == CursorKind.TRANSLATION_UNIT:
                continue

            for token in node.get_tokens():
                # But we can apply a simple heuristic: look at the tokens that
                # appear in a translation unit - and check if you find a
                # mention of a function (in the global set, which we've
                # computed by now) If so, mark this as a 'used' function.

                potential_func_name = token.spelling.strip()
                # Avoid including the function definition as a 'usage'
                if potential_func_name != node.spelling \
                        and potential_func_name in \
                        set_of_all_functions_in_binary \
                        and potential_func_name not in result:

                    # print('[#]', potential_func_name, 'is mentioned in',
                    #       node.spelling, 'at', node.location)
                    result.add(potential_func_name)
        res_queue.put(result)

    res_queue = multiprocessing.Queue()  # type: Any
    list_of_processes = []  # type: List[Any]
    running_instances = 0
    for idx, t_unit in enumerate(t_units):
        print("[-] %3d%% Navigating AST and collecting symbols... " % (
            100*(1+idx)/len(t_units)))
        if running_instances >= multiprocessing.cpu_count():
            for func in res_queue.get():
                used_functions.add(func)
            all_are_still_alive = True
            while all_are_still_alive:
                for idx_proc, proc in enumerate(list_of_processes):
                    child_alive = proc.is_alive()
                    all_are_still_alive = all_are_still_alive and child_alive
                    if not child_alive:
                        del list_of_processes[idx_proc]
                        break
                else:
                    time.sleep(1)
            running_instances -= 1
        proc = multiprocessing.Process(
            target=process_unit, args=(t_unit,))
        list_of_processes.append(proc)
        proc.start()
        running_instances += 1
    for proc in list_of_processes:
        proc.join()
        if proc.exitcode != 0:
            print("[x] Failure in one of the child processes...")
            sys.exit(1)
        for func in res_queue.get():
            used_functions.add(func)


def parse_files(list_of_files: List[str]) -> Tuple[Any, List[Any]]:
    """
    Use Clang to parse the provided list of files, and return
    a tuple of the Clang index, and the list of compiled ASTs
    (one for each compilation unit)
    """
    idx = Index.create()
    t_units = []  # type: List[Any]

    # To avoid parsing the files all the time, store the parsed ASTs
    # of each compilation unit in a cache.
    if not os.path.exists(".cache"):
        os.mkdir(".cache")
    for i, filename in enumerate(list_of_files):
        cache_filename = '.cache/' + os.path.basename(filename) + "_cache"
        # Have I parsed this file before?
        if os.path.exists(cache_filename):
            # Yes, load from cache
            try:
                t_units.append(
                    TranslationUnit.from_ast_file(
                        cache_filename, idx))
                print("[-] Loading cached AST for", filename)
            except TranslationUnitLoadError:
                print("[-] %3d%% Parsing " % (
                    100*(i+1)/len(list_of_files)) + filename)
                t_units.append(idx.parse(filename))
                t_units[-1].save(cache_filename)
        else:
            # No, parse it now.
            print("[-] %3d%% Parsing " % (
                100*(i+1)/len(list_of_files)) + filename)
            t_units.append(idx.parse(filename))
            t_units[-1].save(cache_filename)
    return idx, t_units


def main() -> None:
    """
    Parse all passed-in C files (preprocessed with -E, to be standalone).
    Then scout for mentions of functions at any place, to collect the
    *actually* used functions.

    Finally, report the unused ones.

    The first command line argument expected is the ELF (so we can gather
    the entire list of functions in the object code). The remaining ones
    are the preprocessed C source files.
    """
    if len(sys.argv) <= 2:
        print("Usage:", sys.argv[0], "ELF", "preprocessed_source_files")
        sys.exit(1)

    print("[-] Extracting list of functions from ELF...")

    elf_filename = sys.argv[1]
    #
    # One would expect the list of Function symbols reported by objdump -t
    # to be the perfect source of truth in terms of the complete set of
    # functions in the binary.
    #
    # Alas, that's not the case. Very surprisingly, the following command
    # emits symbols that exist *nowhere* in the disassembled output.
    # I mean nowhere - there's no definition, no reference, nothing.
    #
    cmd = G_PLATFORM_PREFIX + 'objdump -t "' + elf_filename + '" '
    if os.system(cmd + ">/dev/null") != 0:
        print("Failed to launch " + G_PLATFORM_PREFIX + "objdump...")
        sys.exit(1)
    cmd += '| grep "F  *\\.text" ' + "| awk '{print $NF}'"
    set_of_all_functions_per_objdump_t_in_binary = set(
        func_name.strip() for func_name in os.popen(cmd).readlines())

    print("[-] Cleaning up list of functions from ELF...")

    # So to clean this list up, we instead collect the symbols that appear
    # as "<symbolName>:" in the disassembled output...
    cmd = G_PLATFORM_PREFIX + 'objdump -d -S "' + elf_filename + '" '
    function_name_pattern = re.compile(r'^(\S+) <([a-zA-Z0-9_]+?)>:')
    set_of_all_functions_in_binary = set()
    for line in os.popen(cmd).readlines():
        line = line.strip()
        match = function_name_pattern.match(line)
        if match:
            # Don't include addresses of non-function symbols
            maybe_function_name = match.group(2)
            if maybe_function_name in \
                    set_of_all_functions_per_objdump_t_in_binary:
                set_of_all_functions_in_binary.add(maybe_function_name)

    _, t_units = parse_files(sys.argv[2:])

    used_functions = set()  # type: Set[str]

    # To debug what happens with a specific compilation unit, use this:
    #
    # le_units = [x for x in t_units if x.spelling.endswith('svc191vnir.c')]
    # import ipdb ; ipdb.set_trace()

    parse_ast(t_units, set_of_all_functions_in_binary, used_functions)

    # This addresses all mentions of functions in the code we compile.
    # This still doesn't suffice, though - because if one of the C files
    # calls a function we don't have the source code of (e.g. ep_FOO)
    # and this function in turn calls ep_BAR, then ep_BAR is *not*
    # a dead function - even though it doesn't appear anywhere in any
    # of the C sources.
    #
    # So we will also collect the "mentions" made in the disassembly
    cmd = G_PLATFORM_PREFIX + 'objdump -d -S "' + elf_filename + '" '
    function_name_pattern = re.compile(r'^(\S+) <([a-zA-Z0-9_]+?)>:')
    any_mention_pattern = re.compile(r'<([a-zA-Z0-9_]+?)>')

    for line in os.popen(cmd).readlines():
        line = line.strip()
        match = function_name_pattern.match(line)
        if match:
            pass  # Ignore line that define a new function
        else:
            match = any_mention_pattern.search(line)
            if match:
                used_functions.add(match.group(1))

    # We report the results of set subtraction between the
    # set of all functions that exist in the final binary and the
    # ones that were actually used in the source tree.
    print("[-] Generating output: 'deadFunctions' file...")
    open('deadFunctions', 'w').write('\n'.join(
        sorted(set_of_all_functions_in_binary - used_functions)))
    print("[-] Done.")


if __name__ == "__main__":
    main()
