"""Every behaviour number the workday mode uses, each with the source it comes from.

Code reads values with ``P("name")``. The source and a confidence letter travel with each value, so
``python -m agent rules`` prints the table for the judges and the report, and a reader can see at a
glance which numbers are measured and which are our own design choices.

Confidence key:
  H  checked in the primary paper or dataset
  M  checked, but adapted, or a solid secondary source
  L  our own computation on coarse data, or an inference anchored to a source
  D  design value: no published measurement, chosen by us (a guess with a reason)
  U  unverified, do not present as sourced

A ``behaviour:`` section in config/default.yaml can override any value by name (for example after
measuring something on the VM), without code changes.
"""
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Param:
    value: Any
    source: str
    confidence: str
    group: str = ""


def _group(name: str, rows: dict) -> dict:
    return {key: Param(p.value, p.source, p.confidence, name) for key, p in rows.items()}


_TABLE: dict[str, Param] = {}

_TABLE.update(_group("Typing", {
    "typing.wpm_range": Param((48.0, 58.0), "Dhakal 2018 (136M keystrokes, 168k people): mean 51.56 WPM, SD 20.2; one office worker per run drawn near the mean", "H"),
    "typing.iki_per_wpm": Param(12000.0, "Standard conversion: 5 characters per word, so gap in ms = 12000 / WPM", "H"),
    "typing.iki_floor_ms": Param(60.0, "Dhakal 2018: fastest gaps about 60 ms", "H"),
    "typing.iki_sigma": Param(0.42, "CMU keystroke benchmark: log SD 0.46 to 0.60 pooled; one person a bit tighter (our inference)", "L"),
    "typing.word_initial_factor": Param(1.4, "Crump, Lai and Brosowsky: first letter of a word 229 ms vs 147 ms", "M"),
    "typing.repeat_factor": Param(0.85, "Dhakal 2018: repeated letter 176 ms vs about 208 ms", "M"),
    "typing.same_hand_factor": Param(1.04, "Dhakal 2018: switching hands saves 5 to 20 ms", "M"),
    "typing.alternate_hand_factor": Param(0.96, "Dhakal 2018: switching hands saves 5 to 20 ms", "M"),
    "typing.left_hand_factor": Param(1.03, "Dhakal 2018: left hand 7 to 15 ms slower", "M"),
    "typing.letter_to_digit_factor": Param(2.1, "CMU benchmark: letter to digit 289 ms vs about 135 ms (our computation)", "L"),
    "typing.shift_lead_ms": Param(200.0, "CMU benchmark: Shift to letter median 201 ms (our computation)", "L"),
    "typing.shift_lead_sigma": Param(0.45, "CMU benchmark per digraph log SD (our computation)", "L"),
    "typing.chunk_boundary_factor": Param(1.3, "West 2017: people pause at . / @ - in identifiers (direction only, size is ours)", "D"),
    "typing.hold_mean_ms": Param(116.0, "Dhakal 2018: each key held down 116.24 ms on average, SD 23.88", "H"),
    "typing.hold_sigma": Param(0.21, "Dhakal 2018: SD 23.88 on a mean of 116 is a log SD of about 0.2", "H"),
    "typing.hold_clamp_ms": Param((50.0, 250.0), "Safety clamp around Dhakal 2018's 80 to 150 ms range", "D"),
    "typing.rollover_p": Param(0.25, "Dhakal 2018: about 25% of keys are pressed before the previous key is released", "H"),
    "typing.rollover_overlap_ms": Param(30.0, "Dhakal 2018: the overlap is about 30 ms, up to 100 ms", "H"),
    "typing.error_rate_prose": Param(0.043, "Per letter slip rate, measured in our simulator to give 6.3% Backspace in prose (Dhakal 2018: 6.3% of keystrokes are Backspace). Was 0.03 = only 4.4% (VM test 25 Oct: too few typos)", "L"),
    "typing.error_rate_exact": Param(0.03, "URLs, file names, cells: slips happen there too but are always fixed (our rule from the report)", "D"),
    "typing.error_types": Param({"substitution": 53, "omission": 26, "insertion": 21}, "Dhakal 2018: wrong letter 1.65%, missing letter 0.80%, extra letter 0.67%", "M"),
    "typing.detect_lag_weights": Param([46, 28, 11, 7, 8], "Crump and Logan 2012: slip noticed after 0/1/2/3/4+ more keys", "H"),
    "typing.detect_lag_tail_extra": Param((0, 2), "Crump and Logan 2012 only say '4 or more'; how far past 4 is ours", "D"),
    "typing.uncorrected_share": Param(0.07, "Crump and Logan 2012: 93% of slips get corrected, so 7% stay in prose", "H"),
    "typing.error_key_factor": Param(1.3, "Crump and Logan 2012: the wrong key itself 201 ms vs 154 ms before it", "H"),
    "typing.first_backspace_ms": Param(416.0, "Crump and Logan 2012: the first Backspace is the slowest key, 416 ms", "H"),
    "typing.later_backspace_factor": Param(0.6, "Crump and Logan 2012: later Backspaces are fast (only plotted, so the factor is ours)", "U"),
    "typing.after_fix_ms": Param(255.0, "Crump and Logan 2012: first correct key after fixing 255 ms", "H"),
    "typing.modifier_release_s": Param((0.02, 0.09), "Gap between letting go of the key and of Ctrl/Alt in a shortcut", "D"),
    "typing.sentence_pause_sigma": Param(0.7, "Spread of the pause at a sentence end (Conijn 2019 shape, spread ours)", "D"),
    "typing.sentence_extra_compose_ms": Param(74.0, "Conijn 2019: writing your own email vs copying, +74 ms between sentences", "H"),
    "typing.sentence_long_pause_p": Param(0.30, "Hall, Baaijen and Galbraith 2022: 31 to 45% of sentence ends get a long pause", "M"),
    "typing.sentence_long_pause_s": Param((5.5, 0.5, 2.5, 20.0), "Hall 2022: long sentence-end pauses about 5.5 to 7.8 s", "M"),
    "typing.word_extra_compose_ms": Param(36.0, "Conijn 2019: composing vs copying, +36 ms between words", "H"),
    "typing.within_word_compose_ms": Param(-12.0, "Conijn 2019: inside a word composing is 11.7 ms faster", "H"),
    "typing.pburst_words": Param((8.5, 3.0, 2, 20), "Chenoweth and Hayes 2001: people write in bursts of about 9 words", "M"),
    "typing.pburst_pause_s": Param((2.5, 0.55, 1.0, 12.0), "Pause between bursts 2 to 10 s (Chenoweth and Hayes 2001 via main's notes; spread ours)", "M"),
    "typing.paragraph_pause_s": Param((7.0, 0.4, 4.0, 18.0), "Longer pause at a paragraph break, 5 to 15 s (design anchored to the 2 s pause convention)", "D"),
    "typing.arrow_repeat_s": Param((0.5, 0.033), "Holding an arrow key: Windows default repeat delay 0.5 s (setting 1 of 0..3) and about 30 repeats per second", "M"),
}))

_TABLE.update(_group("Editing (messy writing)", {
    "edit.compose_delete_share": Param(0.18, "Crossley 2024: people delete about 18% of what they type when composing, about 5% when copying", "M"),
    "edit.forget_word_p": Param(0.35, "Chance per sentence of leaving out a word and going back for it later. KLiCKe (4,992 adults): about 1 jump back into the text per minute of writing, mostly to insert words; 0.12 gave only about 0.25 a minute (25 Oct)", "L"),
    "edit.extra_word_p": Param(0.07, "Chance per sentence of typing a word that then gets deleted. Size is ours, kept so total deleting stays near Crossley's 18%", "D"),
    "edit.park_p": Param(0.5, "Chance per note piece (3 sentences) of blocking: cut a sentence out, park it on its own line, later paste it back or delete it. Judges asked for it (21 Oct); no study gives a rate. Set so about 2 in 3 runs of 15 min show it (simulator, 25 Oct; 0.10 showed it about once in five)", "D"),
    "edit.park_keep_p": Param(0.65, "Chance the parked sentence is pasted back rather than deleted; ours", "D"),
    "edit.rewrite_p": Param(0.4, "Chance per note piece of a rewrite attempt: push the last sentence to its own line, try a second version, keep one. Judges asked for it; no study gives a rate. Set so about 3 in 5 runs of 15 min show it (simulator, 25 Oct)", "D"),
    "edit.rewrite_keep_new_p": Param(0.6, "Chance the new version wins the rewrite attempt; ours", "D"),
    "edit.clean_leftover_p": Param(0.5, "After a cut, chance a stray space or comma is left and then cleaned up; ours", "D"),
    "edit.fix_delay_words": Param((5, 25), "How many words later the bot goes back for the forgotten word: about one minute of composing at about 20 words a minute (KLiCKe gives only the per minute rate)", "L"),
    "edit.reread_s": Param((1.5, 0.5, 0.6, 6.0), "Pause to reread before going back into the text; anchored to KLM mental step 1.35 s", "L"),
}))

_TABLE.update(_group("Pauses", {
    "klm.M": Param(1.35, "Card, Moran and Newell 1980: one mental step (deciding) 1.35 s", "M"),
    "klm.sigma": Param(0.70, "Card, Moran and Newell 1980: spread of the mental step, CV about 0.8", "M"),
    "pause.reading_s": Param((2.0, 6.0), "Reading or thinking pause 2 to 6 s (workshop 2 checklist)", "M"),
    "pause.resume_lag_s": Param((1.0, 0.18), "Monk, Trafton and Boehm-Davis 2008: about 1 to 1.5 s to get going again after switching back to a task", "M"),
}))

_TABLE.update(_group("To do list", {
    "todo.items_by_minutes": Param([(10, (2, 3)), (30, (3, 4)), (60, (3, 5)), (100000, (4, 6))],
                                   "Work items at the start for a run of up to N minutes. Raised for short runs on 25 Oct: with 1 or 2 lines a 5 min run ran out of work at 2:24 (VM test)", "D"),
    "todo.top_up_min_left_s": Param(60.0, "When the list is empty, add a line if at least this much time is left after the final update (was 150 s; a short run ended 2.5 min early)", "D"),
    "todo.personal_items": Param((0, 2), "0 to 2 personal items like 'call dentist' (Kellyn's report); Bellotti 2004: lists mix work and personal", "D"),
    "todo.personal_min_minutes": Param(10, "Personal items only on runs of 10 min or more, so a 3 min demo stays on work; ours", "D"),
    "todo.out_of_order_p": Param(0.25, "Chance the next task is not the next line on the list. Czerwinski 2004: only 19% of task switches come from the person's own to do list order", "L"),
    "todo.strike_now_p": Param(0.6, "Chance an item is struck right after the task, otherwise at a later visit to the list; ours", "D"),
    "todo.save_after_edit_p": Param(0.5, "Chance the list is saved right after an edit; otherwise a later visit or the final update saves it. No study measures how often people press Ctrl+S (searched 25 Oct); ours", "D"),
    "todo.glance_p": Param(0.25, "Chance of Alt+Tabbing to the list just to look at it between tasks; ours (no rate found)", "D"),
    "todo.add_when_open_below": Param(2, "Add new items when fewer than this many are open (report: 'when the list runs low'); ours", "D"),
    "todo.add_count": Param((1, 2), "How many items get added at a time; ours", "D"),
    "todo.delete_p": Param(0.2, "Chance an open item gets deleted over the run (report: about 1 in 5, reminders that turned out unnecessary); ours", "D"),
    "todo.resume_p": Param(0.77, "Mark, Gonzalez and Harris 2005: 77% of interrupted work is resumed the same day", "H"),
    "todo.end_reserve_s": Param(15.0, "Base seconds kept free at the end for the final list update, plus about 6 s per open line and 5 s per open window (timed in our simulator)", "L"),
    "todo.progress_line_min_minutes": Param(5, "Runs longer than 5 min get a '2 of 4 done' line (report)", "D"),
    "todo.max_line_chars": Param(80, "A to do line with its note stays under about 80 characters so it never wraps in Writer", "D"),
}))

_TABLE.update(_group("Breaks", {
    "break.per_hour": Param(3.0, "Glasgow 2014 (105 office staff, sensors for a week): people get up about 3 times an hour, 29 times a day", "H"),
    "break.short_s": Param((30.0, 300.0), "Eijckelhof 2014: a short computer break is 30 s to 5 min with no keyboard or mouse", "H"),
    "break.onscreen_s": Param((60.0, 300.0), "On screen personal break (a personal site) 1 to 5 min; ours, same range as a short break", "D"),
    "break.onscreen_share": Param(0.4, "Share of breaks spent on a personal site instead of away; ours", "D"),
    "break.max_sitting_s": Param(1200.0, "Glasgow 2014: 80% of sitting stretches end before 20 min", "H"),
    "break.lunch_s": Param((1800.0, 2700.0), "OfficeTeam 2018: average lunch 39 min, so 30 to 45 min", "M"),
    "break.lunch_after_h": Param(6.0, "Singapore MOM: a meal break after 6 hours of work, so lunch only on runs over 6 h", "H"),
    "break.sitting_s": Param((660.0, 0.9, 180.0, 2700.0), "Time at the desk before getting up: lognormal median 11 min, log SD 0.9 (clamp 3 to 45 min). Our fit so that about 75 to 80% of stretches end before 20 min and there are about 3 a hour (Glasgow 2014)", "L"),
    "break.fifteen_min_count": Param((0, 1), "15 min run: 0 or 1 on screen break (agreed 23 Oct)", "D"),
}))

_TABLE.update(_group("Tasks", {
    "task.weights": Param({"hybrid": 0.40, "websurf": 0.40, "office": 0.15, "explorer": 0.05},
                          "How often each task kind is picked, tuned in the simulator so about half the time is in the browser (TechTarget survey: about 56% of the day in a browser, weak source)", "L"),
    "task.min_seconds": Param({"crypto_prices": 110, "crypto_compare": 130, "read_note": 120, "laptop_compare": 60, "browse": 50, "writer_note": 110, "calc_sheet": 75, "tidy_files": 35},
                              "Shortest usual length of each task kind, measured in our simulator (10th percentile); a task only starts if this still fits before the end", "L"),
    "task.write_s_per_char": Param(0.8, "Seconds per character when composing a note with pauses and edits, timed in our simulator (median 0.66, 90th percentile 0.79, 25 Oct); the slow end is used so a long write is not started just before the end", "L"),
    "task.row_need_s": Param(80.0, "A crypto sheet row (look up a coin on one or two sites, type it) plus the save, with no end of day check inside; timed in our simulator (about 50 s row + 25 s save)", "L"),
    "task.page_give_up_s": Param(20.0, "Give up on a blank or broken page after about 20 s. Pena Moreno 2020: only 14% give up by 10 s; 20 s is ours", "D"),
    "task.reload_p": Param(0.5, "Chance of one reload before giving up; ours", "D"),
    "task.courses_to_look": Param((1, 3), "Websurf: look at 1 to 3 items (report)", "D"),
    "task.coins_to_record": Param((2, 4), "Coins typed into Calc in the CoinGecko task (report)", "D"),
    "task.rows_to_add": Param((3, 6), "Rows added to a budget sheet; ours", "D"),
    "task.files_to_tidy": Param((2, 3), "Files moved or renamed when tidying (report)", "D"),
    "task.interrupt_p": Param(0.25, "Chance a long task is cut by a break or another task and left 'started'. Mark 2005: work is interrupted often (57% of working spheres); our size", "L"),
    "doc.close_done_p": Param(0.5, "Chance a finished Writer document is closed (Writer itself stays open for the to do list); ours", "D"),
    "task.look_again_after_s": Param(240.0, "A task left started because a site had no data (Coinbase prices) is looked at again only after about 4 min, once; ours", "D"),
    "plan.linked_office_p": Param(0.33, "Share of runs where the guaranteed office task grows out of the hybrid (e.g. 'send crypto summary to tom' after the crypto sheet), written from what it found (Kellyn, 25 Oct); ours", "D"),
    "copy.calc_p": Param(0.8, "Share of numbers copied off the page (select, Ctrl+C, Ctrl+V) instead of read and typed; people mix both, no rate found; 0.5 raised to 0.8 on Kellyn's call (25 Oct): copying is how people usually move numbers into a sheet", "D"),
    "copy.notes_p": Param(0.5, "Share of note lines copied off the page instead of typed after looking (when lists.copy is on). No desktop study found: a phone study saw little pasting (0.7 a day), a vendor blog claims over 1000 copy pastes a week with no method; so 50/50 is ours", "D"),
    "copy.repeat_p": Param(0.4, "Share of copies where Ctrl+C is pressed 2 or 3 times to be sure; a common habit (Raymond Chen, Windows Latest 2026), no measured rate", "D"),
    "tabs.max_open": Param(6, "Dubroy 2010: median open tabs 6 or fewer for 20 of 21 people", "M"),
    "tabs.close_some_p": Param(0.43, "Dubroy 2010: 12 of 21 people did not bother closing tabs, so 9 of 21 do", "M"),
}))

_TABLE.update(_group("Between tasks", {
    "gap.lognormal_median_s": Param(8.0, "Pause between tasks: mix of short and long idle gaps, anchored to Halfaker 2015", "L"),
    "gap.lognormal_sigma": Param(0.9, "Mixture design (gives a spread CV about 1.5 with the idle part)", "L"),
    "gap.idle_weight": Param(0.20, "Share of long idle gaps, anchored to Dezso 2006 heavy tail", "L"),
    "gap.idle_range_s": Param((20.0, 240.0), "Long idle gaps 20 s to 4 min; ours", "L"),
    "gap.idle_alpha": Param(0.2, "Heavy tail exponent (Dezso 2006)", "L"),
    "gap.targets": Param({"cv": (1.0, 2.0)}, "Goh and Barabasi 2008: human gap CV 1 to 2; workshop asks CV above 0.4", "M"),
}))


_overrides: dict[str, Any] = {}


def configure(overrides: dict | None) -> None:
    """Apply ``behaviour:`` overrides from config. Unknown names are rejected so typos fail loudly."""
    _overrides.clear()
    for name, value in (overrides or {}).items():
        if name not in _TABLE:
            raise KeyError(f"unknown behaviour parameter: {name}")
        _overrides[name] = tuple(value) if isinstance(value, list) and isinstance(_TABLE[name].value, tuple) else value


def P(name: str) -> Any:
    """Value of a behaviour parameter (override if configured)."""
    return _overrides[name] if name in _overrides else _TABLE[name].value


def table() -> list[tuple[str, Any, str, str, str]]:
    """Rows of (group, name, value, source, confidence)."""
    return [(spec.group, name, P(name), spec.source, spec.confidence) for name, spec in _TABLE.items()]


def markdown() -> str:
    """The parameters table as markdown, one section per group."""
    out, group = [], None
    for g, name, value, source, conf in table():
        if g != group:
            out += ["", f"### {g}", "", "| Rule | Value | Where the number comes from | Kind |", "|---|---|---|---|"]
            group = g
        kind = {"H": "research", "M": "research (adapted)", "L": "our computation from research",
                "D": "our guess (design)", "U": "unverified"}[conf]
        out.append(f"| `{name}` | {value} | {source} | {kind} |")
    return "\n".join(out).strip() + "\n"
