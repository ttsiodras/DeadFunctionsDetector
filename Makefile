TARGET:=detect_unused_functions.py
export PYTHONPATH:=/usr/lib/python2.7/dist-packages/

all:	.processed

.processed:	${TARGET}
	flake8 $<
	pylint $<
	mypy --ignore-missing-imports $<
	touch $@
