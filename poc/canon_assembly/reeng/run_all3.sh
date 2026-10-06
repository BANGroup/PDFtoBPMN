#!/bin/bash
cd /home/budnik_an/Obligations/poc/canon_assembly/reeng
for x in "B1/КД-РД-Б1.041-04 d041" "B1/ДП-Б1.024-06 d024" "V4/РГ-184-06 d184" "V5/КД-РД-В5.058-04 d058" "B1/КД-ДП-Б1.011-04 d011"; do ./run_one.sh $x; done
