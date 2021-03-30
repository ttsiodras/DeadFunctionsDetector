TARGET:=detect_unused_functions.py
PYTHON:=python3

all:	.processed

check:
	@if [ -z "$$VIRTUAL_ENV" ] ; then                         \
	    echo "============================================" ; \
	    echo "[x] You are not running inside a virtualenv." ; \
	    echo "[x] Please run 'make dev-install'" ;            \
	    echo "============================================" ; \
	    exit 1 ;                                              \
	fi

.processed:	${TARGET}
	@$(MAKE) -s flake8
	@$(MAKE) -s pylint
	@$(MAKE) -s mypy
	@touch $@

flake8: | check
	echo "============================================"
	echo " Running flake8..."
	echo "============================================"
	flake8 ${TARGET}

pylint: | check
	echo "============================================"
	echo " Running pylint..."
	echo "============================================"
	pylint ${TARGET}

mypy: | check
	echo "============================================"
	echo " Running mypy..."
	echo "============================================"
	mypy --ignore-missing-imports ${TARGET}

dev-install:
	@${PYTHON} -c 'import sys; sys.exit(1 if (sys.version_info.major<3 or sys.version_info.minor<5) else 0)' || { \
	    echo "=============================================" ; \
	    echo "[x] You need at least Python 3.5 to run this." ; \
	    echo "=============================================" ; \
	    exit 1 ; \
	}
	@if [ ! -d .venv ] ; then                                  \
	    echo "[-] Installing VirtualEnv environment..." ;      \
	    ${PYTHON} -m venv .venv || exit 1 ;                    \
	    echo "[-] Installing packages inside environment..." ; \
	    . .venv/bin/activate || exit 1 ;                       \
	    python3 -m pip install -r requirements.txt || exit 1 ; \
	    echo "=============================================" ; \
	    echo "[-] You now need to activate the environment " ; \
	    echo "[-] Just do this:"                             ; \
	    echo "[-]        . .venv/bin/activate"               ; \
	    echo "=============================================" ; \
	fi

clean:
	rm -rf .cache/ .mypy_cache/ .processed

.PHONY:	flake8 pylint mypy clean dev-install
