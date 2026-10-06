"""Полный прогон: план -> Word -> проверка. python run_doc.py <папка> <slug> [--nocompare] [--skipword]"""
import sys, subprocess, os
d, slug = sys.argv[1], sys.argv[2]
py = sys.executable
if '--skipplan' not in sys.argv: subprocess.run([py, 'reeng_plan.py', d, slug], check=True)
if '--skipword' not in sys.argv:
    subprocess.run([py, 'run_word_steps.py', slug] + ([] if '--nocompare' in sys.argv else ['--compare']), check=True)
subprocess.run([py, 'reeng_check.py', d, slug], check=True)
