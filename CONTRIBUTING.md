# Contributing

Thanks for helping! This project is a collection of *small* practice labs - keep new labs short, concrete and checkable.

## Ground rules for a lab
* **One clear scenario**, English text with an explicit "EXPECTED RESULT"; say what must be left alone (e.g. "do not touch process X").
* **Check the real system state**, not what the learner typed. Return requirements with `R(label, ok, detail)`.
* **Be safe**: everything a lab creates must be named `lab-*` / `lab_*` or live under `/opt/linux-lab` so `cleanup_all()` removes it.
  Back up real system files with `save_orig(path)` before editing them. Never enable a real firewall or touch the real sshd.
* Randomise data where possible so a reset gives a fresh variant.
* Never rely on `chown` for tasks about special permission bits (it clears SUID/SGID).

## Workflow
1. Add your lab to the right `course/modules/mNN_*.py` (or create a new module file; ids are `MNN-Tn`, exams `MNN-Xn`).
2. `python3 run.py --validate` - must report 0 problems and runs without root.
3. Try the lab on a throw-away Debian VM, including a reset and a wrong answer.
4. Open a pull request that says which Debian release you tested on.
