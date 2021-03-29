#!/usr/bin/env python2
"""
A utility that parses pre-processed (standalone) C files using Clang,
and then detects and reports all functions inside an ELF that are
not used anywhere.
"""
from __future__ import print_function

import re
import os
import sys

# For mypy static type checks.
from typing import Set, List, Tuple, Any  # NOQA

from clang.cindex import (
    CursorKind, Index, TranslationUnit, TranslationUnitLoadError)


def parse_calls(t_units, cursor_work):
    # type: (List[Any], Any) -> None
    """
    Also, collect all defined functions' names.
    """
    for t_unit in t_units:
        # Gather all the calls made by functions in this C file
        for node in t_unit.cursor.walk_preorder():
            cursor_work(node)


def parse_files(list_of_files):
    # type: (List[str]) -> Tuple[Any, List[Any]]
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
    for filename in list_of_files:
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
                print("[-] Parsing", filename)
                t_units.append(idx.parse(filename))
                t_units[-1].save(cache_filename)
        else:
            # No, parse it now.
            print("[-] Parsing", filename)
            t_units.append(idx.parse(filename))
            t_units[-1].save(cache_filename)
    return idx, t_units


def main():
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
    cmd = 'sparc-rtems-objdump -t "' + elf_filename + '" '
    cmd += '| grep "F  *\\.text" ' + "| awk '{print $NF}'"
    set_of_all_functions_per_objdump_t_in_binary = set(
        func_name.strip() for func_name in os.popen(cmd).readlines())

    # So to clean this list up, we instead collect the symbols that appear
    # as "<symbolName>:" in the disassembled output...
    cmd = 'sparc-rtems-objdump -d -S "' + elf_filename + '" '
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

    def collect_function_mentions(node):
        """
        To find the unused functions, we need to collect all 'mentions'
        of functions anywhere. This is generally speaking, a hard problem.
        But... (see below)
        """
        if node.kind == CursorKind.TRANSLATION_UNIT:
            return

        for token in node.get_tokens():
            # But we can apply a simple heuristic: look at the tokens that
            # appear in a translation unit - and check if you find a mention
            # of a function (in the global set, which we've computed by now)
            # If so, mark this as a 'used' function.
            potential_func_name = token.spelling.strip()
            # Avoid including the function definition as a 'usage'
            if potential_func_name != node.spelling \
                    and potential_func_name in set_of_all_functions_in_binary \
                    and potential_func_name not in used_functions:
                print('[#]', potential_func_name, 'is mentioned in',
                      node.spelling, 'at', node.location)
                used_functions.add(potential_func_name)

    # To debug what happens with a specific compilation unit, use this:
    #
    # le_units = [x for x in t_units if x.spelling.endswith('svc191vnir.c')]
    # import ipdb ; ipdb.set_trace()

    parse_calls(t_units, collect_function_mentions)

    # This addresses all mentions of functions in the code we compile.
    # This still doesn't suffice, though - because if one of the C files
    # calls a function we don't have the source code of (e.g. ep_FOO)
    # and this function in turn calls ep_BAR, then ep_BAR is *not*
    # a dead function - even though it doesn't appear anywhere in any
    # of the C sources.
    #
    # So we will also collect the "mentions" made in the disassembly
    cmd = 'sparc-rtems-objdump -d -S "' + elf_filename + '" '
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
    open('deadFunctions', 'w').write('\n'.join(
        sorted(set_of_all_functions_in_binary - used_functions)))


if __name__ == "__main__":
    main()