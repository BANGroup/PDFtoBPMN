#!/bin/bash
# usage: run_one.sh <подпуть в СМК> <slug>
cd /home/budnik_an/Obligations/poc/canon_assembly/reeng
B=../../../data/bnd_corpus/documents/СМК; P=../../../venv/bin/python
D=$B/$1; N=$(basename $1)
L=/tmp/run_$2.log
$P reeng_plan.py $D $2 > $L 2>&1
$P run_word_steps.py $2 --assemble >> $L 2>&1
PDF=$(ls $D/files/*[Ээ]талон*.pdf | head -1)
$P numfix.py $2 "$PDF" >> $L 2>&1
$P run_word_steps.py $2 --final >> $L 2>&1
$P reeng_check.py $D $2 >> $L 2>&1
$P finish.py $N $2 >> $L 2>&1
echo done_$2 >> /tmp/run_one.status
