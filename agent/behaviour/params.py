"""Every behaviour number the agent uses, each with the source it comes from.

This table is the single place where human behaviour is parameterised. Code reads values with
``P("name")``; nothing in the input, pacing or skill modules hard-codes a timing. The source and
confidence travel with each value so ``python -m agent params`` can print the table that goes in
the write-up, and so a reviewer can see at a glance which numbers are measured and which are
design choices. Full citations and derivations are in ../docs/behaviour-model.md.

Confidence key (same as the report):
  H  verified in the primary text
  M  verified but adapted, or a solid secondary source
  L  team computation on coarse data, or an inference anchored to a source
  D  design value with no published measurement
  U  unverified, do not present as sourced

A ``behaviour:`` section in config/default.yaml can override any value by name, which is how a
VM measurement (for example pixels per wheel notch) replaces an assumption without code changes.
"""
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Param:
    value: Any
    source: str
    confidence: str


_TABLE: dict[str, Param] = {
    # Typing (Dhakal et al. 2018, CHI, 136M keystrokes; CMU benchmark fits; Crump and Logan 2012; Conijn 2019)
    "typing.wpm_range": Param((50.0, 60.0), "Dhakal 2018: population 51.56 WPM, SD 20.2; office persona", "H"),
    "typing.iki_per_wpm": Param(12000.0, "Dhakal 2018; IKI ms = 12000 / WPM (team conversion)", "H"),
    "typing.iki_floor_ms": Param(60.0, "Dhakal 2018: lower bound about 60 ms", "H"),
    "typing.iki_sigma": Param(0.42, "CMU digraph log-SD 0.46 to 0.60 pooled; within-person 0.35 to 0.5 inferred", "L"),
    "typing.word_initial_factor": Param(1.35, "Dhakal 2018 direction (word-initial keys slow); magnitude", "U"),
    "typing.repeat_factor": Param(0.85, "Dhakal 2018: letter repetition 176 vs about 208 ms", "M"),
    "typing.same_hand_factor": Param(1.04, "Dhakal 2018: alternation saves 5 to 20 ms", "M"),
    "typing.alternate_hand_factor": Param(0.96, "Dhakal 2018: alternation saves 5 to 20 ms", "M"),
    "typing.left_hand_factor": Param(1.03, "Dhakal 2018: left hand 7 to 15 ms slower", "M"),
    "typing.letter_to_digit_factor": Param(2.1, "CMU: e->5 289 ms vs about 135 ms letter digraphs (team computation)", "L"),
    "typing.shift_lead_ms": Param(200.0, "CMU: Shift->r median 201 ms (team computation)", "L"),
    "typing.shift_lead_sigma": Param(0.45, "CMU per-digraph log-SD (team computation)", "L"),
    "typing.chunk_boundary_factor": Param(1.3, "West 2017: pauses at delimiters in identifiers (direction only)", "D"),
    "typing.familiar_factor": Param(0.73, "CMU: same password 27% faster session 1 vs 8 (team computation)", "L"),
    "typing.hold_mean_ms": Param(116.0, "Dhakal 2018: keypress duration 116.24 ms, SD 23.88", "H"),
    "typing.hold_sigma": Param(0.25, "Dhakal 2018 SD 23.88 on mean 116 (log-SD about 0.2 to 0.25)", "H"),
    "typing.hold_clamp_ms": Param((40.0, 250.0), "Dhakal 2018: 80 to 150 ms even for slow typists; safety clamp", "D"),
    "typing.rollover_p": Param(0.25, "Dhakal 2018: rollover on 25% (SD 17%) of keystrokes", "H"),
    "typing.rollover_overlap_ms": Param(30.0, "Dhakal 2018: overlap about 30 ms, up to 100 ms", "H"),
    "typing.error_rate_prose": Param(0.03, "Derived to match Dhakal 2018: 1.17% uncorrected, 6.3% correction keys", "L"),
    "typing.error_rate_exact": Param(0.02, "URLs, filenames, cells: errors happen but are always corrected (design)", "D"),
    "typing.error_types": Param({"substitution": 53, "omission": 26, "insertion": 21}, "Dhakal 2018: 1.65/0.80/0.67%", "M"),
    "typing.detect_lag_weights": Param([46, 28, 11, 7, 8], "Crump and Logan 2012: caught after 0/1/2/3/4+ keys", "H"),
    "typing.uncorrected_share": Param(0.07, "Crump and Logan 2012: 93% of errors corrected", "H"),
    "typing.error_key_factor": Param(1.3, "Crump and Logan 2012: error key 201 ms vs 154 ms before", "H"),
    "typing.first_backspace_ms": Param(416.0, "Crump and Logan 2012: first Backspace slowest key, 416 ms", "H"),
    "typing.later_backspace_factor": Param(0.6, "Crump and Logan 2012: later Backspaces fast (rate only plotted)", "U"),
    "typing.after_fix_ms": Param(255.0, "Crump and Logan 2012: first correct key after fixing 255 ms", "H"),
    "typing.detect_lag_tail_extra": Param((0, 2), "Crump and Logan 2012 report only '4 or more'; spread of the tail is design", "D"),
    "typing.modifier_release_s": Param((0.02, 0.09), "Gap between releasing the key and the modifier in a shortcut; design", "D"),
    "typing.sentence_pause_sigma": Param(0.7, "Conijn 2019 sentence-boundary pauses; log-SD design", "D"),
    "typing.sentence_extra_compose_ms": Param(74.0, "Conijn 2019: email vs copy +74.10 ms between sentences", "H"),
    "typing.sentence_long_pause_p": Param(0.10, "Writing research 2 s pause convention; 10% rate design", "D"),
    "typing.sentence_long_pause_s": Param((2.0, 6.0), "Leijten and Van Waes 2 s threshold; range design", "D"),
    "typing.word_extra_compose_ms": Param(36.0, "Conijn 2019: email vs copy +36.31 ms between words", "H"),
    "typing.within_word_compose_ms": Param(-12.0, "Conijn 2019: within-word IKI 11.69 ms faster when composing", "H"),
    "typing.pburst_words": Param((8.5, 2, 20), "Chenoweth and Hayes 2001: P-bursts about 9 words (secondary)", "M"),
    "typing.pburst_pause_s": Param((2.5, 2.0, 10.0), "2 s pause threshold convention; magnitudes design", "D"),
    "typing.paragraph_pause_s": Param((5.0, 15.0), "Design, anchored to the 2 s pause convention", "D"),

    # Cognitive pauses (KLM, Card, Moran and Newell 1980; Monk 2008; Mark 2016; Sauro)
    "klm.M": Param(1.35, "Card, Moran and Newell 1980: mental preparation 1.35 s (via Wikipedia)", "M"),
    "klm.H": Param(0.40, "Card, Moran and Newell 1980: home hands keyboard <-> mouse 0.4 s", "M"),
    "klm.P": Param(1.10, "Card, Moran and Newell 1980: point with the mouse 1.1 s", "M"),
    "klm.B": Param(0.10, "Card, Moran and Newell 1980: button press 0.1 s", "M"),
    "klm.sigma": Param(0.40, "KLM gives means only; lognormal jitter 0.3 to 0.5 is design", "D"),
    "web.click_composite_s": Param(3.73, "Sauro: click a link or button 3.73 s mean (via Wikipedia)", "M"),
    "resume.a_ms": Param(1032.0, "Monk, Trafton and Boehm-Davis 2008: lag = 1032 + 189.4 ln(s)", "M"),
    "resume.b_ms": Param(189.4, "Monk 2008 (log base inferred natural)", "M"),
    "resume.sigma": Param(0.18, "Monk 2008: SD 231 on 1548 ms", "M"),
    "focus.median_s": Param(40.0, "Mark 2016: median screen focus 40.2 s, mean 47 s", "M"),
    "focus.sigma": Param(0.57, "Mark 2016 mean/median ratio (team computation)", "M"),

    # Session rhythm (Barabasi 2005, Dezso 2006, Halfaker 2015, Goh and Barabasi 2008)
    "gap.lognormal_median_s": Param(8.0, "Mixture anchored to Halfaker 2015 within-session modes; weight design", "L"),
    "gap.lognormal_sigma": Param(0.9, "Mixture design (gives CV 1.5 with the idle part)", "L"),
    "gap.idle_weight": Param(0.20, "Mixture design, anchored to Dezso 2006 alpha 1.2 heavy tail", "L"),
    "gap.idle_range_s": Param((20.0, 240.0), "Mixture design", "L"),
    "gap.idle_alpha": Param(0.2, "Truncated Pareto survival exponent (density about 1.2, Dezso 2006)", "L"),
    "gap.idle_drift": Param(0.25, "Vigilance: more lapses later in a session; magnitude design", "D"),
    "gap.targets": Param({"cv": (1.0, 2.0), "B": (0.0, 0.33), "mem": 0.15}, "Goh and Barabasi 2008; Mark 2005 CV 1.6 to 2.2", "M"),

    # Mouse (Soukoreff and MacKenzie 2004; Balabit team computations; Huang 2012)
    "mouse.throughput_bits_s": Param((3.7, 4.9), "Soukoreff and MacKenzie 2004: ISO 9241-9 mouse throughput", "H"),
    "mouse.intercept_s": Param((0.10, 0.23), "Soukoreff and MacKenzie 2004: Shannon-form intercepts 107 to 230 ms", "H"),
    "mouse.mt_sigma": Param(0.12, "Per-move jitter, design", "D"),
    "mouse.scatter_div": Param(6.0, "Endpoint SD = W/6 (humans W/4.133, about 4% misses; Soukoreff 2004)", "M"),
    "mouse.primary_reach": Param((0.88, 0.97), "Balabit: primary movement covers median 90% (team computation)", "L"),
    "mouse.overshoot": Param((0.34, 200.0, 1.02, 1.10), "Balabit: 34.1% of moves over 200 px overshoot (team computation)", "L"),
    "mouse.primary_time_share": Param((0.75, 0.85), "Consistent with Meyer 1988 optimised submovements; design", "D"),
    "mouse.skew_k": Param((0.80, 0.92), "BeCAPTCHA: human velocity profiles asymmetric; k design", "D"),
    "mouse.curve_offset": Param((0.04, 0.12), "Balabit straightness median 0.83 (team computation)", "L"),
    "mouse.event_hz": Param((60.0, 100.0), "Balabit move events about 64 Hz (team computation)", "L"),
    "mouse.preclick_fast": Param((0.6, 0.02, 0.12), "Balabit move-to-press median 31 ms (team computation)", "L"),
    "mouse.preclick_slow": Param((0.30, 0.6, 2.0), "Balabit move-to-press p75 187 ms, p95 1.5 s (team computation)", "L"),
    "mouse.click_hold": Param((0.095, 0.35, 0.05, 0.30), "Balabit: hold median 94 ms, p95 171 ms (team computation)", "L"),
    "mouse.step_jitter": Param((0.8, 1.2), "Jitter on the interval between move events; design", "D"),
    "mouse.idle_chunk_s": Param((1.0, 4.0), "Length of one resting/examining spell while reading; Huang 2012 counts idle as still >= 1 s", "D"),
    "mouse.examine_px": Param((140, 60), "Size of a small examining move (x, y); Huang 2012 median cursor-gaze distance 143 px", "L"),
    "mouse.trace_px": Param((120, 320, 6), "Tracing move along a line: length range and vertical wobble (px); design", "D"),
    "mouse.idle_actions": Param({"park": 0.588, "examine": 0.329, "trace": 0.025, "pre_click": 0.057},
                                "Huang, White and Buscher 2012: cursor states while reading", "H"),
    "mouse.gaze_lag_s": Param((0.25, 0.70), "Huang 2012: cursor lags gaze at least 250 ms, mean 700 ms", "H"),

    # Scrolling and reading (NN/g 2018; Chartbeat; Chromium; Brysbaert 2019; Nielsen 2008)
    "read.wpm": Param((238.0, 51.2, 150.0, 350.0), "Brysbaert 2019: 238 wpm, SD 51.2", "H"),
    "read.fraction_beta": Param((2.0, 8.0), "Nielsen 2008: users read about 20% of words (Beta fit design)", "M"),
    "read.look_around_s": Param((1.0, 3.0), "Design", "D"),
    "read.words_per_screen": Param({"article": 200, "product": 35, "hub": 60}, "Design by page type", "D"),
    "scroll.screen_attention": Param([0.57, 0.17, 0.07, 0.05, 0.04, 0.03], "NN/g 2018: 57% screen 1, 74% within 2, 81% within 3", "H"),
    "scroll.depth_product": Param([0.30, 0.30, 0.20, 0.10, 0.06, 0.04], "NN/g 2018 decay of attention by screen (team inference)", "L"),
    "scroll.depth_news": Param((0.10, 0.10, 3.0, 2.2), "Chartbeat via Slate: 10% never scroll; Beta fit (team)", "L"),
    "scroll.notch_px": Param(100.0, "Chromium: 3 lines x 33.3 px per notch; verify on VM", "H"),
    "scroll.notches_per_screen": Param((9, 10), "1080p at 100% scale (team inference)", "L"),
    "scroll.burst_read": Param([2, 3, 3, 4, 4, 5], "No field log exists; derived from reading dwell", "D"),
    "scroll.burst_skim": Param([3, 4, 5, 6, 7, 8], "No field log exists", "D"),
    "scroll.up_p": Param(0.12, "Re-read bursts, design", "D"),
    "scroll.notch_gap_ms": Param((55.0, 18.0, 15.0), "Design", "U"),
    "scroll.glance_s": Param((0.67, 0.5, 0.2, 3.0), "Look at newly revealed lines after a burst (median, log-SD, clamp); design", "D"),
    "scroll.reread_s": Param((1.0, 0.5, 0.4, 4.0), "Pause after an upward re-read burst; design", "D"),
    "scroll.article_screens": Param((6, 14), "Article length in screens; design", "D"),
    "scroll.min_screen_s": Param(2.5, "Minimum seconds per screen viewed, ties depth to dwell; design", "D"),
    "scroll.reread_notches": Param((1, 3), "Upward re-read burst size; design", "D"),
    "scroll.hand_region": Param((0.25, 0.70, 0.30, 0.70), "Where the hand puts the cursor on the page before wheeling (x and y fractions); design", "D"),
    "scroll.keyboard_p": Param(0.07, "5 to 10%; wheel dominates (Alexander and Cockburn 2008 direction)", "D"),

    # Browsing (Liu 2010; Weinreich 2008; Dubroy 2010; Kumar and Tomkins 2010; Granka 2004)
    "page.dwell_weibull": Param({"hub": (0.58, 14.0), "product": (0.62, 22.0), "article": (0.72, 35.0)},
                                "Liu 2010 shape k<1; Weinreich 2008 quantile fit (team computation)", "M"),
    "page.dwell_clamp_s": Param((1.5, 150.0), "Weinreich 2008: nearly 10% of views over 2 min", "M"),
    "page.revisit_factor": Param(0.75, "Shorter dwell on revisits (team inference from Weinreich 2008)", "L"),
    "nav.mix": Param({"link": 0.55, "back": 0.10, "switch_tab": 0.08, "typed": 0.12, "reload": 0.02, "find": 0.12, "forward": 0.01},
                     "Weinreich 2008 Table I, Dubroy 2010; site search replaced by find-on-page offline", "M"),
    "nav.new_tab_persona": Param((0.04, 0.14, 13, 8), "Dubroy 2010: 4 vs 14 tabs per 100 navigations (13 vs 8 of 21 users)", "H"),
    "nav.max_tabs": Param(6, "Dubroy 2010: median open tabs 6 or fewer for 20 of 21 users", "M"),
    "nav.link_above_fold_w": Param(3.0, "Weinreich 2008: 76.5% of clicked links visible at load", "M"),
    "nav.link_upper_left_w": Param(1.8, "Weinreich 2008: 45% of clicks in a 520x400 upper-left area", "M"),
    "nav.sites_per_block": Param((3, 4), "Inferred from Kumar and Tomkins 2010 same-site share", "L"),
    "nav.pages_per_site_mean": Param(3.0, "1 + Exp(mean 3), inferred from Kumar and Tomkins 2010", "L"),
    "nav.block_s": Param((240.0, 420.0), "Design", "D"),
    "nav.partial_host": Param((0.7, 2, 4), "Obendorf 2007: some users type a prefix and accept autocomplete", "D"),
    "nav.dead_page_dwell_s": Param((0.7, 3.0, 1.0, 12.0), "Weibull shape, scale, clamp on an error page before going back; design", "D"),
    "nav.interest_weight": Param(2.0, "Extra weight for a link matching what the person came for; design", "D"),
    "nav.after_ctrl_l_s": Param((0.15, 0.4), "Gap between Ctrl+L and the first typed key; design", "D"),
    "nav.after_find_open_s": Param((0.2, 0.6), "Gap after the find bar opens or closes; design", "D"),
    "nav.ctrl_click_lead_s": Param((0.08, 0.25), "Ctrl held before the click in Ctrl+click; design", "D"),
    "nav.close_tabs_first_p": Param(0.5, "Chance of closing background tabs one by one before the window; design", "D"),
    "nav.between_tab_close_s": Param((0.3, 1.0), "Gap between successive Ctrl+W presses; design", "D"),
    "launch.weights": Param({"taskbar": 4.0, "start_search": 3.0, "run_dialog": 0.0}, "Researcher synthesis taskbar 40 / Start search 30 (n = 8 study)", "U"),

    # Spreadsheet (Panko 2000/2007/2015; Wiseman 2011; KLM arithmetic; LibreOffice/AOO help)
    "sheet.digit_slip_p": Param(0.013, "Wiseman 2011: one corrected slip per 70.6 to 77.1 digits (iPad)", "M"),
    "sheet.digit_key_s": Param((0.40, 0.3, 0.25, 0.9), "10-key 6k to 12k keystrokes/h; letter-to-digit 289 ms (team)", "L"),
    "sheet.row_pause": Param((1.4, 2.2, 0.4), "KLM M 1.35 s before each row (first row longer) (team)", "L"),
    "sheet.formula_pause": Param((2.0, 0.4), "KLM M plus Olson and Nilsen 1987 address-scanning pause (team)", "L"),
    "sheet.check_pause": Param((2.5, 0.4, 1.5, 4.0), "Checking results; anchored to Panko checking findings", "D"),
    "sheet.mid_row_hesitation": Param((0.25, 0.9), "Hesitation inside a row; design", "D"),
    "sheet.after_jump_s": Param((0.2, 0.5), "Gap after Ctrl+Home before selecting; design", "D"),
    "sheet.bold_mouse_p": Param(0.6, "Toolbar vs Ctrl+B; direction from Lane 2005 (Word users)", "D"),

    # System response the agent waits for (not human behaviour; the person waits for the machine)
    "system.start_menu_s": Param((0.4, 0.9), "Start menu opening on the VM; design", "D"),
    "system.search_response_s": Param((0.5, 1.2), "Windows search results appearing; design (Enter too early runs Bing)", "D"),
    "system.poll_s": Param((0.2, 0.45), "How often the agent re-reads the window title while waiting (perception, not behaviour)", "D"),
    "system.dialog_s": Param((0.4, 1.0), "Save dialog opening; design", "D"),

    # Task mix (Mark 2016 shares, renormalised without email)
    "session.priority_p": Param(0.9, "Barabasi 2005 priority-queue model: highest priority task with p = 0.9", "M"),
    "session.task_weights": Param({"web_surfing": 0.45, "office_writer": 0.35, "office_calc": 0.20},
                                  "Mark 2016 screen-time shares, email removed and renormalised (team)", "L"),
}


_overrides: dict[str, Any] = {}


def configure(overrides: dict | None) -> None:
    """Apply ``behaviour:`` overrides from config. Unknown names are rejected, so typos fail loudly."""
    _overrides.clear()
    for name, value in (overrides or {}).items():
        if name not in _TABLE:
            raise KeyError(f"unknown behaviour parameter: {name}")
        _overrides[name] = tuple(value) if isinstance(value, list) and isinstance(_TABLE[name].value, tuple) else value


def P(name: str) -> Any:
    """Value of a behaviour parameter (override if configured)."""
    return _overrides[name] if name in _overrides else _TABLE[name].value


def table() -> list[tuple[str, Any, str, str]]:
    """Rows of (name, value, source, confidence) for the write-up."""
    return [(name, P(name), spec.source, spec.confidence) for name, spec in _TABLE.items()]


def markdown() -> str:
    """The parameters table as markdown."""
    lines = ["| Parameter | Value | Source | Confidence |", "|---|---|---|---|"]
    for name, value, source, confidence in table():
        lines.append(f"| `{name}` | {value} | {source} | {confidence} |")
    return "\n".join(lines)
