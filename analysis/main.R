suppressPackageStartupMessages({
  library(dplyr)
  library(tidyr)
  library(readr)
  library(purrr)
  library(tibble)
  library(stringr)
  library(forcats)
  library(ggplot2)
  library(scales)
  library(patchwork)
  library(ggbeeswarm)
  library(ARTool)
})

DIR_DATA  <- file.path("experiments", "gl1")
DIR_FIG   <- file.path("analysis", "figures")
DIR_TAB   <- file.path("analysis", "tables")
DIR_STATS <- file.path("analysis", "stats")

for (d in c(DIR_FIG, DIR_TAB, DIR_STATS)) {
  dir.create(d, recursive = TRUE, showWarnings = FALSE)
}

ALPHA <- 0.05

TREAT_LEVELS <- c("baseline", "slim", "blafs", "confine")
TREAT_LABELS <- c("Baseline", "SlimToolkit", "BLAFS", "Confine")
DEBLOATERS   <- TREAT_LEVELS[-1]

treat_factor <- function(x) factor(x, levels = TREAT_LEVELS, labels = TREAT_LABELS)

PAL_TREAT <- c(
  "Baseline"    = "#4D4D4D",
  "SlimToolkit" = "#E69F00",
  "BLAFS"       = "#0072B2",
  "Confine"     = "#009E73"
)

PAL_PARADIGM <- c(
  "File removal"          = "#0072B2",
  "System-call restriction" = "#009E73"
)

PAL_SEQ <- c("#FBE9E7", "#F6C6B8", "#C9DCEA", "#7FB0D3", "#2A6F97")

BASE_SIZE <- 8

theme_thesis <- function(base_size = BASE_SIZE) {
  theme_bw(base_size = base_size, base_family = "sans") +
    theme(
      panel.grid.minor   = element_blank(),
      panel.grid.major.x = element_blank(),
      panel.grid.major.y = element_line(linewidth = 0.25, colour = "grey88"),
      panel.border       = element_rect(linewidth = 0.35, colour = "grey55"),
      strip.background   = element_rect(fill = "grey94", colour = "grey55",
                                        linewidth = 0.35),
      strip.text         = element_text(size = base_size, margin = margin(2.2, 2.2, 2.2, 2.2)),
      axis.text          = element_text(size = base_size - 0.5, colour = "grey20"),
      axis.title         = element_text(size = base_size),
      axis.ticks         = element_line(linewidth = 0.3, colour = "grey55"),
      legend.key.size    = unit(7, "pt"),
      legend.text        = element_text(size = base_size),
      legend.title       = element_text(size = base_size),
      legend.margin      = margin(0, 0, 0, 0),
      legend.box.spacing = unit(3, "pt"),
      plot.title         = element_text(size = base_size, face = "bold", hjust = 0),
      plot.margin        = margin(2, 3, 2, 2)
    )
}

theme_set(theme_thesis())
update_geom_defaults("point", list(size = 0.75))

W_COL  <- 3.33
W_FULL <- 7.00

save_fig <- function(plot, name, width, height) {
  pdf_path <- file.path(DIR_FIG, paste0(name, ".pdf"))
  png_path <- file.path(DIR_FIG, paste0(name, ".png"))
  ggsave(pdf_path, plot, width = width, height = height,
         device = grDevices::cairo_pdf)
  ggsave(png_path, plot, width = width, height = height, dpi = 600)
  message("  figure: ", pdf_path, "  (", width, " x ", height, " in)")
  invisible(pdf_path)
}

`%||%` <- function(a, b) if (is.null(a)) b else a

fmt_p <- function(p) {
  ifelse(is.na(p), "--",
    ifelse(p < 1e-3,
      sprintf("$%s$", sub("e-0?", "\\\\times 10^{-", sprintf("%.1e", p)) %>%
                        paste0("}")),
      sub("^0", "", sprintf("%.3f", p))))
}

fmt_num <- function(x, digits = 2) {
  ifelse(is.na(x), "--", formatC(x, format = "f", digits = digits, big.mark = ","))
}

write_stat <- function(df, name) {
  path <- file.path(DIR_STATS, paste0(name, ".csv"))
  readr::write_csv(df, path)
  message("  stats:  ", path, "  (", nrow(df), " rows)")
  invisible(path)
}

VIOLIN_MIN   <- 6L
CROSSBAR_MIN <- 4L

LABEL_JIT <- position_jitter(width = 0.13, height = 0, seed = 20260821)

dist_layers <- function(df, xvar = "treatment", yvar = "delta",
                        fillvar = "treatment", labels_below = 4L,
                        panelvars = character(0)) {
  df <- df %>% group_by(across(all_of(c(panelvars, xvar)))) %>%
    mutate(.n_grp = n()) %>% ungroup()
  big  <- df %>% filter(.n_grp >= VIOLIN_MIN)
  mid  <- df %>% filter(.n_grp >= CROSSBAR_MIN, .n_grp < VIOLIN_MIN)
  smal <- df %>% filter(.n_grp <  CROSSBAR_MIN)

  out <- list()
  if (nrow(big)) {
    out <- c(out, list(
      geom_violin(data = big, aes(fill = .data[[fillvar]]), colour = NA,
                  alpha = 0.32, width = 0.88, trim = TRUE, adjust = 1.1,
                  show.legend = FALSE),
      geom_boxplot(data = big, width = 0.15, fill = "white", colour = "grey20",
                   linewidth = 0.3, outlier.shape = NA, show.legend = FALSE)
    ))
  }
  if (nrow(mid)) {
    out <- c(out, list(
      stat_summary(data = mid, fun = median, geom = "errorbar",
                   aes(ymin = after_stat(y), ymax = after_stat(y)),
                   width = 0.46, linewidth = 0.42, colour = "grey20",
                   show.legend = FALSE)
    ))
  }
  out <- c(out, list(
    ggbeeswarm::geom_quasirandom(
      aes(colour = .data[[fillvar]]), width = 0.26,
      method = "quasirandom", groupOnX = TRUE,
      size = 0.85, alpha = 0.9, stroke = 0, show.legend = FALSE
    )
  ))
  if (nrow(smal) && labels_below > 0) {
    out <- c(out, list(
      ggrepel::geom_text_repel(
        data = smal, aes(label = subject), position = LABEL_JIT,
        size = BASE_SIZE * 0.26, colour = "grey25", segment.size = 0.2,
        min.segment.length = 0, max.overlaps = Inf, box.padding = 0.25,
        seed = 20260821, show.legend = FALSE)
    ))
  }
  out
}

n_axis_labels <- function(df, xvar = "treatment", levels_all = TREAT_LABELS[-1]) {
  cnt <- df %>% count(.data[[xvar]], name = "n")
  setNames(
    vapply(levels_all, function(l) {
      k <- cnt$n[match(l, as.character(cnt[[xvar]]))]
      k <- if (is.na(k)) 0L else k
      paste0(l, "\n(n=", k, ")")
    }, character(1)),
    levels_all
  )
}

panel_delta <- function(o_id, data = deltas, title = NULL, show_x = TRUE,
                        compact_x = FALSE) {
  o <- OUTCOMES %>% filter(id == o_id)
  d <- data %>%
    filter(outcome == o_id) %>%
    mutate(treatment = treat_factor(as.character(treatment)))
  d$treatment <- droplevels(factor(d$treatment, levels = TREAT_LABELS[-1]))

  present <- TREAT_LABELS[match(intersect(DEBLOATERS, outcome_treatments(o_id)),
                                TREAT_LEVELS)]

  ylab <- if (o$norm == "pct") "Change from baseline (%)"
          else paste0("Change from baseline (", o$unit, ")")

  axis_labels <- n_axis_labels(d, levels_all = present)
  if (compact_x && "SlimToolkit" %in% names(axis_labels)) {
    axis_labels[["SlimToolkit"]] <- sub("SlimToolkit", "Slim\nToolkit",
                                         axis_labels[["SlimToolkit"]], fixed = TRUE)
  }

  ggplot(d, aes(x = factor(as.character(treatment), levels = present), y = delta)) +
    geom_hline(yintercept = 0, linetype = "22", colour = "grey40", linewidth = 0.3) +
    dist_layers(d) +
    scale_x_discrete(limits = present, labels = axis_labels) +
    scale_fill_manual(values = PAL_TREAT, guide = "none") +
    scale_colour_manual(values = PAL_TREAT, guide = "none") +
    labs(title = title %||% o$label, x = NULL, y = ylab) +
    theme(axis.text.x = if (show_x) element_text() else element_blank())
}

message("[1] loading warm-runtime campaign")

warm_raw <- bind_rows(
  read_csv(file.path(DIR_DATA, "single_warm",        "run_table.csv"), show_col_types = FALSE),
  read_csv(file.path(DIR_DATA, "stack_warm",         "run_table.csv"), show_col_types = FALSE),
  read_csv(file.path(DIR_DATA, "stack_warm_confine", "run_table.csv"), show_col_types = FALSE)
)

stopifnot(nrow(warm_raw) == 1600L)

warm <- warm_raw %>%
  mutate(
    correct = if_else(subject == "sock-shop", passed_cold_only, passed),
    treatment = factor(treatment, levels = TREAT_LEVELS)
  )

warm <- warm %>%
  mutate(
    fail_stage = case_when(
      correct                                  ~ NA_character_,
      !is.na(error) & error == "image_absent"  ~ "Build failure",
      !is.na(error) & str_detect(error, "^(TimeoutError|DockerError)") ~ "Start failure",
      !is.na(error) & str_detect(error, "^RuntimeError: up failed")    ~ "Start failure",
      !is.na(error)                            ~ "Workload failure",
      cold_match_eff %in% FALSE | steady_match_eff %in% FALSE ~ "Output mismatch",
      TRUE                                     ~ "Unclassified"
    )
  )

subject_meta <- warm %>%
  distinct(track, subject, kind, workload_category) %>%
  mutate(
    stratum = if_else(kind == "oneshot", "one-shot", "load-driven"),
    request_driven = kind %in% c("influx", "memcached", "neo4j", "service", "stack"),
    workload = recode(workload_category,
      "general-service" = "General-purpose",
      "serverless-base" = "Serverless",
      "ml"              = "Machine learning",
      "data-intensive"  = "Data-intensive",
      "stack"           = "Application stack"
    )
  )

WORKLOAD_LEVELS <- c("General-purpose", "Serverless", "Machine learning",
                     "Data-intensive", "Application stack")

OUTCOMES <- tribble(
  ~id,             ~column,                 ~label,                    ~unit, ~norm,  ~scope,     ~phase,
  "warm_energy",   "total_energy_sut_j",    "Warm-runtime energy",     "J",   "pct",  "all",      "Warm runtime",
  "warm_duration", "total_duration_s",      "Warm-runtime duration",   "s",   "pct",  "all",      "Warm runtime",
  "warm_power",    "total_power_sut_w",     "Warm-runtime power",      "W",   "abs",  "all",      "Warm runtime",
  "steady_j_req",  "steady_j_per_request",  "Energy per request",      "J",   "pct",  "request",  "Warm runtime",
  "cpu",           "cpu_sut_0_7_pct",       "CPU utilization",         "pp",  "abs",  "all",      "Warm runtime",
  "peak_mem",      "peak_memory_mb",        "Peak memory",             "MB",  "pct",  "single",   "Warm runtime"
)

OUTCOMES <- OUTCOMES %>% mutate(campaign = "warm")

in_scope <- function(scope, meta) {
  switch(scope,
    "all"         = rep(TRUE, nrow(meta)),
    "load-driven" = meta$stratum == "load-driven",
    "request"     = meta$request_driven,
    "one-shot"    = meta$stratum == "one-shot",
    "single"      = meta$track == "single"
  )
}

warm_meta <- warm %>%
  left_join(subject_meta, by = c("track", "subject", "kind", "workload_category")) %>%

  mutate(total_power_sut_w = total_energy_sut_j / total_duration_s) %>%

  mutate(steady_j_per_request = if_else(steady_subres, NA_real_,
                                        steady_j_per_request))

trial_long <- map_dfr(seq_len(nrow(OUTCOMES)), function(i) {
  o <- OUTCOMES[i, ]
  d <- warm_meta
  d$in_scope <- in_scope(o$scope, d)
  d %>%
    filter(in_scope, correct) %>%
    transmute(
      outcome = o$id, track, subject, workload, stratum,
      treatment, rep,
      value = .data[[o$column]]
    ) %>%
    filter(!is.na(value))
})

variant_correct <- warm %>%
  group_by(subject, treatment) %>%
  summarise(any_correct = any(correct), .groups = "drop")

cells <- trial_long %>%
  group_by(outcome, track, subject, workload, stratum, treatment) %>%
  summarise(n_rep = n(), value = median(value), .groups = "drop")

norm_lookup <- setNames(OUTCOMES$norm, OUTCOMES$id)

deltas <- cells %>%
  group_by(outcome, subject) %>%
  filter(any(treatment == "baseline")) %>%
  mutate(base = value[treatment == "baseline"]) %>%
  ungroup() %>%
  mutate(
    norm  = norm_lookup[outcome],
    delta = if_else(norm == "pct", 100 * (value - base) / base, value - base)
  ) %>%
  filter(treatment != "baseline") %>%
  mutate(treatment = droplevels(treatment))

message("    warm trials: ", nrow(warm), " | correct: ", sum(warm$correct),
        " | cells: ", nrow(cells), " | deltas: ", nrow(deltas))

message("[2] loading cold-pull campaign (raw traces)")

DIR_COLD <- file.path(DIR_DATA, "cold_eb")
RAPL_INTERVAL_S <- 0.100
EB_LEAD_S       <- 0.18

cold_run_table <- file.path(DIR_COLD, "run_table.csv")
if (!file.exists(cold_run_table) ||
    length(list.dirs(DIR_COLD, recursive = FALSE)) < 1140L) {
  archive <- file.path(DIR_COLD, "cold_pull_campaign_results.tgz")
  if (!file.exists(archive)) stop("cold-pull run table and archive are both missing")
  unpack_dir <- tempfile("cold-data-")
  dir.create(unpack_dir)
  utils::untar(archive, exdir = unpack_dir)
  unpacked <- file.path(unpack_dir, "cold_pull_campaign")
  copied <- file.copy(list.files(unpacked, full.names = TRUE), DIR_COLD,
                      recursive = TRUE, overwrite = FALSE)
  unlink(unpack_dir, recursive = TRUE)
  if (!file.exists(cold_run_table)) stop("cold-pull archive extraction failed")
}

cold_rt <- read_csv(cold_run_table, show_col_types = FALSE) %>%
  rename(run_id = `__run_id`, done = `__done`) %>%
  mutate(rep = as.integer(sub("^.*_repetition_", "", run_id)))

stopifnot(nrow(cold_rt) == 1140L, all(cold_rt$done == "DONE"))

window_power <- function(t, cum, t0, t1) {
  if (length(t) < 2L) return(NA_real_)
  a <- suppressWarnings(max(which(t <= t0)))
  b <- suppressWarnings(min(which(t >= t1)))
  if (!is.finite(a)) a <- 1L
  if (!is.finite(b)) b <- length(t)
  if (b <= a) b <- min(a + 1L, length(t))
  if (b <= a) return(NA_real_)
  span <- t[b] - t[a]
  if (!is.finite(span) || span <= 0) return(NA_real_)
  d <- cum[b] - cum[a]
  if (!is.finite(d) || d < 0) return(NA_real_)
  d / span
}

integrate_trial <- function(run_id, duration_s) {
  rapl_path <- file.path(DIR_COLD, run_id, "rapl.csv")
  eb_path   <- file.path(DIR_COLD, run_id, "energibridge.csv")
  if (!file.exists(rapl_path) || !file.exists(eb_path)) {
    return(tibble(run_id = run_id, node_w = NA_real_, pkg0_w = NA_real_,
                  pkg1_w = NA_real_, eb_pkg0_w = NA_real_, n_rapl = 0L,
                  t_start = NA_real_))
  }

  head2 <- readLines(eb_path, n = 2L, warn = FALSE)
  eb_anchor <- if (length(head2) == 2L) {
    hdr <- strsplit(head2[1], ",", fixed = TRUE)[[1]]
    val <- strsplit(head2[2], ",", fixed = TRUE)[[1]]
    suppressWarnings(as.numeric(val[match("Time", hdr)]) / 1000)
  } else NA_real_

  r <- read.csv(rapl_path)
  t <- r$wall_ms / 1000
  if (!is.finite(eb_anchor)) eb_anchor <- t[1] + 0.30
  t0 <- eb_anchor + EB_LEAD_S
  t1 <- t0 + duration_s

  eb <- suppressWarnings(readr::read_csv(
    eb_path, col_select = c("Time", "PACKAGE_ENERGY (J)"),
    show_col_types = FALSE, progress = FALSE))

  tibble(
    run_id    = run_id,
    pkg0_w    = window_power(t, r$pkg0_j, t0, t1),
    pkg1_w    = window_power(t, r$pkg1_j, t0, t1),
    eb_pkg0_w = window_power(eb$Time / 1000, eb$`PACKAGE_ENERGY (J)`, t0, t1),
    n_rapl    = nrow(r),

    t_start   = t[1]
  ) %>%
    mutate(node_w = pkg0_w + pkg1_w)
}

cold_integrated <- map2_dfr(cold_rt$run_id, cold_rt$pull_seconds, integrate_trial)

cold_trials <- cold_rt %>%
  left_join(cold_integrated, by = "run_id") %>%
  mutate(
    duration_s   = pull_seconds,
    energy_node  = node_w * duration_s,
    energy_eb    = eb_pkg0_w * duration_s,
    intensity    = if_else(size_mb > 0, energy_node / size_mb, NA_real_),
    treatment    = factor(treatment, levels = TREAT_LEVELS)
  )

cold_trials <- cold_trials %>%
  arrange(t_start) %>%
  mutate(exec_order = row_number())

cold_drift <- cold_trials %>%
  filter(!is.na(node_w)) %>%
  group_by(subject, treatment) %>%
  mutate(power_residual = node_w - median(node_w)) %>%
  ungroup()

cold_drift_test <- {
  ct <- suppressWarnings(cor.test(cold_drift$exec_order, cold_drift$power_residual,
                                  method = "spearman", exact = FALSE))
  tibble(n = nrow(cold_drift), rho = unname(ct$estimate), p_raw = ct$p.value)
}

cold_order_balance <- cold_trials %>%
  group_by(treatment) %>%
  summarise(n = n(), median_position = median(exec_order),
            q1 = quantile(exec_order, .25), q3 = quantile(exec_order, .75),
            .groups = "drop") %>%
  mutate(treatment = treat_factor(as.character(treatment)))

cold_verify <- cold_trials %>%
  filter(!is.na(energy_node), !is.na(energy_node_j), energy_node_j > 0) %>%
  mutate(ratio = energy_node / energy_node_j,
         band = cut(duration_s, breaks = c(0, .5, 1, 5, 30, Inf),
                    labels = c("<0.5 s", "0.5--1 s", "1--5 s", "5--30 s", ">30 s"),
                    right = FALSE)) %>%
  group_by(band) %>%
  summarise(n = n(),
            median_ratio = median(ratio),
            median_power_raw = median(node_w),
            median_power_recorded = median(power_node_w), .groups = "drop")

cold_key_verify <- list(
  n_trials   = nrow(cold_trials),
  n_energy   = sum(!is.na(cold_trials$energy_node)),
  n_eb       = sum(!is.na(cold_trials$energy_eb)),
  n_wrapped  = sum(is.na(cold_trials$energy_eb)),
  long_ratio = cold_verify$median_ratio[cold_verify$band == ">30 s"],
  short_ratio= cold_verify$median_ratio[cold_verify$band == "<0.5 s"],
  n_short    = sum(cold_trials$duration_s < 0.5),
  n_subres   = sum(cold_trials$duration_s < RAPL_INTERVAL_S * 2),
  drift_rho  = cold_drift_test$rho,
  drift_p    = cold_drift_test$p_raw,
  order_spread = max(cold_order_balance$median_position) -
                 min(cold_order_balance$median_position)
)

cold_channel_agreement <- cold_trials %>%
  filter(!is.na(pkg0_w), !is.na(eb_pkg0_w), pkg0_w > 0) %>%
  summarise(n = n(),
            median_ratio = median(eb_pkg0_w / pkg0_w),
            q05 = quantile(eb_pkg0_w / pkg0_w, .05),
            q95 = quantile(eb_pkg0_w / pkg0_w, .95))

COLD_OUTCOMES <- tribble(
  ~id,             ~column,       ~label,                      ~unit,  ~norm, ~scope, ~phase,          ~campaign,
  "cold_energy",   "energy_node", "Cold-pull node energy",     "J",    "pct", "all",  "Distribution",  "cold",
  "cold_duration", "duration_s",  "Cold-pull duration",        "s",    "pct", "all",  "Distribution",  "cold",
  "cold_intensity","intensity",   "Cold-pull energy intensity","J/MB", "pct", "all",  "Distribution",  "cold"
)

cold_long <- map_dfr(seq_len(nrow(COLD_OUTCOMES)), function(i) {
  o <- COLD_OUTCOMES[i, ]
  cold_trials %>%
    left_join(variant_correct, by = c("subject", "treatment")) %>%
    filter(any_correct) %>%
    left_join(subject_meta %>% select(subject, workload, stratum), by = "subject") %>%
    transmute(outcome = o$id,
              track = if_else(kind == "stack", "stack", "single"),
              subject, workload, stratum, treatment, rep,
              value = .data[[o$column]]) %>%
    filter(!is.na(value))
})

cold_cells <- cold_long %>%
  group_by(outcome, track, subject, workload, stratum, treatment) %>%
  summarise(n_rep = n(), value = median(value), .groups = "drop")

size_cells <- cold_trials %>%
  left_join(variant_correct, by = c("subject", "treatment")) %>%
  filter(any_correct, !is.na(size_mb)) %>%
  left_join(subject_meta %>% select(subject, workload), by = "subject") %>%
  group_by(track = if_else(kind == "stack", "stack", "single"), subject, workload, treatment) %>%
  summarise(size_mb = median(size_mb), .groups = "drop")

size_deltas <- size_cells %>%
  group_by(subject) %>%
  filter(any(treatment == "baseline")) %>%
  mutate(base = size_mb[treatment == "baseline"]) %>%
  ungroup() %>%
  mutate(delta = 100 * (size_mb - base) / base) %>%
  filter(treatment != "baseline") %>%
  mutate(treatment = droplevels(treatment))

message("    cold trials: ", nrow(cold_trials),
        " | integrated: ", cold_key_verify$n_energy,
        " | gated cells: ", nrow(cold_cells) / nrow(COLD_OUTCOMES))

OUTCOMES <- bind_rows(OUTCOMES, COLD_OUTCOMES)
cells    <- bind_rows(cells, cold_cells)

cold_deltas <- cold_cells %>%
  group_by(outcome, subject) %>%
  filter(any(treatment == "baseline")) %>%
  mutate(base = value[treatment == "baseline"]) %>%
  ungroup() %>%
  mutate(norm = "pct", delta = 100 * (value - base) / base) %>%
  filter(treatment != "baseline") %>%
  mutate(treatment = droplevels(treatment))

deltas <- bind_rows(deltas, cold_deltas)

COLD_TREATMENTS <- c("baseline", "slim", "blafs")

outcome_treatments <- function(id) {
  if (OUTCOMES$campaign[match(id, OUTCOMES$id)] == "cold") COLD_TREATMENTS else TREAT_LEVELS
}

signrank_exact <- function(d, max_exact = 20L, n_mc = 2e5L) {
  d <- d[!is.na(d)]
  d <- d[d != 0]
  n <- length(d)
  if (n < 2L) return(list(p = NA_real_, n = n, V = NA_real_, r_rb = NA_real_))

  r  <- rank(abs(d))
  Vp <- sum(r[d > 0])
  Vn <- sum(r[d < 0])
  r_rb <- (Vp - Vn) / (Vp + Vn)

  obs <- abs(Vp - Vn)
  if (n <= max_exact) {
    signs <- as.matrix(expand.grid(rep(list(c(-1, 1)), n)))
    stat  <- abs(as.vector(signs %*% r))
    p <- mean(stat >= obs - 1e-9)
  } else {
    signs <- matrix(sample(c(-1, 1), n * n_mc, replace = TRUE), nrow = n_mc)
    stat  <- abs(as.vector(signs %*% r))
    p <- (sum(stat >= obs - 1e-9) + 1) / (n_mc + 1)
  }
  list(p = p, n = n, V = Vp, r_rb = r_rb)
}

rb_band <- function(r) {
  a <- abs(r)
  case_when(
    is.na(a) ~ NA_character_,
    a <  .10 ~ "negligible",
    a <  .30 ~ "small",
    a <  .50 ~ "medium",
    TRUE     ~ "large"
  )
}

paired_contrast <- function(x, y = NULL, label_a, label_b) {
  if (is.null(y)) {
    subj <- names(x)[!is.na(x)]
    d <- if (length(subj)) x[subj] else numeric(0)
  } else {
    subj <- intersect(names(x)[!is.na(x)], names(y)[!is.na(y)])
    d <- if (length(subj)) x[subj] - y[subj] else numeric(0)
  }
  res <- signrank_exact(as.numeric(d))
  tibble(
    contrast    = paste(label_a, "vs.", label_b),
    a = label_a, b = label_b,
    n_pairs     = length(subj),
    n_nonzero   = res$n,
    median_diff = if (length(d)) median(as.numeric(d)) else NA_real_,
    p_raw       = res$p,
    r_rb        = res$r_rb,
    magnitude   = rb_band(res$r_rb)
  )
}

contrasts_for_outcome <- function(df, debloaters = DEBLOATERS) {
  wide <- df %>%
    select(subject, treatment, delta) %>%
    pivot_wider(names_from = treatment, values_from = delta)
  vec <- function(t) {
    if (!t %in% names(wide)) return(setNames(numeric(0), character(0)))
    setNames(wide[[t]], wide$subject)
  }
  labs <- setNames(TREAT_LABELS[-1], DEBLOATERS)

  base_rows <- map_dfr(debloaters, function(t)
    paired_contrast(vec(t), NULL, labs[[t]], "Baseline"))
  pair_rows <- if (length(debloaters) > 1)
    map_dfr(combn(debloaters, 2, simplify = FALSE), function(p)
      paired_contrast(vec(p[1]), vec(p[2]), labs[[p[1]]], labs[[p[2]]]))
    else tibble()

  bind_rows(base_rows, pair_rows) %>%
    mutate(contrast = factor(contrast, levels = unique(contrast)))
}

friedman_blocked <- function(df, treatments = TREAT_LEVELS) {
  d <- df %>%
    filter(treatment %in% treatments) %>%
    mutate(treatment = factor(as.character(treatment), levels = treatments))
  k <- length(treatments)
  complete <- d %>% count(subject) %>% filter(n == k) %>% pull(subject)
  d <- d %>% filter(subject %in% complete)
  if (length(complete) < 2L) {
    return(tibble(chi2 = NA_real_, df = k - 1L, n_blocks = length(complete),
                  p_raw = NA_real_, k = k))
  }
  m <- d %>%
    arrange(subject, treatment) %>%
    select(subject, treatment, value) %>%
    pivot_wider(names_from = treatment, values_from = value) %>%
    column_to_rownames("subject") %>%
    as.matrix()
  ft <- friedman.test(m)
  tibble(chi2 = unname(ft$statistic), df = unname(ft$parameter),
         n_blocks = nrow(m), p_raw = ft$p.value, k = k)
}

shapiro_safe <- function(x, label = NA_character_) {
  x <- x[!is.na(x)]
  if (length(x) < 3L || length(unique(x)) < 2L) {
    return(tibble(sample = label, n = length(x), W = NA_real_, p = NA_real_,
                  testable = FALSE, rejects = NA))
  }
  st <- shapiro.test(x)
  tibble(sample = label, n = length(x), W = unname(st$statistic),
         p = st$p.value, testable = TRUE, rejects = st$p.value < ALPHA)
}

bh <- function(p) p.adjust(p, method = "BH")

describe6 <- function(x) {
  x <- x[!is.na(x)]
  tibble(n = length(x), mean = mean(x), median = median(x), sd = sd(x),
         min = min(x), max = max(x), variance = var(x))
}

message("[3] RQ1: warm-runtime effects")

rq1_descriptives <- deltas %>%
  group_by(outcome, treatment) %>%
  group_modify(~ describe6(.x$delta)) %>%
  ungroup() %>%
  left_join(OUTCOMES %>% select(id, label, unit, norm), by = c("outcome" = "id")) %>%
  mutate(treatment = treat_factor(as.character(treatment))) %>%
  arrange(match(outcome, OUTCOMES$id), treatment)

rq1_baseline_levels <- cells %>%
  filter(treatment == "baseline") %>%
  group_by(outcome) %>%
  summarise(n = n(), median = median(value), min = min(value), max = max(value),
            min_subject = subject[which.min(value)],
            max_subject = subject[which.max(value)], .groups = "drop") %>%
  left_join(OUTCOMES %>% select(id, label, unit), by = c("outcome" = "id"))

rq1_normality <- bind_rows(

  deltas %>%
    group_by(outcome, treatment) %>%
    group_modify(~ shapiro_safe(.x$delta)) %>%
    ungroup() %>%
    mutate(contrast = paste(treat_factor(as.character(treatment)), "vs. Baseline")) %>%
    select(-sample),

  map_dfr(combn(DEBLOATERS, 2, simplify = FALSE), function(pair) {
    lab <- paste(TREAT_LABELS[match(pair[1], TREAT_LEVELS)], "vs.",
                 TREAT_LABELS[match(pair[2], TREAT_LEVELS)])
    deltas %>%
      filter(treatment %in% pair,
             map_lgl(outcome, ~ all(pair %in% outcome_treatments(.x)))) %>%
      select(outcome, subject, treatment, delta) %>%
      pivot_wider(names_from = treatment, values_from = delta) %>%
      filter(!is.na(.data[[pair[1]]]), !is.na(.data[[pair[2]]])) %>%
      group_by(outcome) %>%
      group_modify(~ shapiro_safe(.x[[pair[1]]] - .x[[pair[2]]], label = lab)) %>%
      ungroup() %>%
      rename(contrast = sample)
  })
) %>%
  select(outcome, contrast, n, W, p, testable, rejects) %>%
  distinct() %>%
  arrange(match(outcome, OUTCOMES$id), contrast)

rq1_omnibus <- cells %>%
  group_by(outcome) %>%
  group_modify(~ friedman_blocked(.x, outcome_treatments(.y$outcome))) %>%
  ungroup()

rq1_omnibus_restricted <- cells %>%
  group_by(outcome) %>%
  group_modify(~ friedman_blocked(.x, c("baseline", "blafs",
                                        if (.y$outcome %in% COLD_OUTCOMES$id) NULL else "confine"))) %>%
  ungroup()

rq1_pairwise <- deltas %>%
  group_by(outcome) %>%
  group_modify(~ contrasts_for_outcome(
    .x, intersect(DEBLOATERS, outcome_treatments(.y$outcome)))) %>%
  ungroup()

rq1_tests <- bind_rows(
  rq1_omnibus %>% transmute(outcome, kind = "omnibus",
                            contrast = paste0("Friedman (", k, " treatments)"),
                            n_pairs = n_blocks, n_nonzero = NA_integer_,
                            statistic = chi2, df, p_raw,
                            r_rb = NA_real_, magnitude = NA_character_,
                            median_diff = NA_real_),
  rq1_pairwise %>% transmute(outcome, kind = "pairwise", contrast = as.character(contrast),
                             n_pairs, n_nonzero, statistic = NA_real_, df = NA_real_,
                             p_raw, r_rb, magnitude, median_diff)
) %>%
  group_by(outcome) %>%
  mutate(p_bh = bh(p_raw), family_size = sum(!is.na(p_raw))) %>%
  ungroup() %>%
  left_join(OUTCOMES %>% select(id, label, unit, norm), by = c("outcome" = "id")) %>%
  arrange(match(outcome, OUTCOMES$id), kind, contrast)

WARM_OUTCOMES <- OUTCOMES$id[OUTCOMES$campaign == "warm"]

rq1_key <- list(
  n_trials          = nrow(warm),
  n_correct         = sum(warm$correct),
  n_subjects        = n_distinct(warm$subject),
  n_outcomes        = nrow(OUTCOMES),
  n_contrasts       = sum(rq1_pairwise$outcome %in% WARM_OUTCOMES),
  n_contrasts_test  = sum(rq1_pairwise$outcome %in% WARM_OUTCOMES & !is.na(rq1_pairwise$p_raw)),
  n_sig_bh          = sum(rq1_tests$outcome %in% WARM_OUTCOMES &
                          rq1_tests$kind == "pairwise" & rq1_tests$p_bh < ALPHA, na.rm = TRUE),
  n_cold_contrasts  = sum(!rq1_pairwise$outcome %in% WARM_OUTCOMES),
  n_cold_test       = sum(!rq1_pairwise$outcome %in% WARM_OUTCOMES & !is.na(rq1_pairwise$p_raw)),
  n_cold_sig        = sum(!rq1_tests$outcome %in% WARM_OUTCOMES &
                          rq1_tests$kind == "pairwise" & rq1_tests$p_bh < ALPHA, na.rm = TRUE),
  n_norm_testable   = sum(rq1_normality$testable),
  n_norm_reject     = sum(rq1_normality$rejects, na.rm = TRUE),
  n_subres_trials   = sum(warm$steady_subres),
  n_omnibus_est     = sum(!is.na(rq1_omnibus$p_raw))
)

message("    figure: warm-runtime effects")

rq1_panels <- map(WARM_OUTCOMES, function(id) {
  panel_delta(id, compact_x = TRUE) +
    theme(axis.text.x = element_text(size = BASE_SIZE - 1.5, lineheight = 0.9))
})
names(rq1_panels) <- WARM_OUTCOMES

fig_rq1 <- wrap_plots(rq1_panels, ncol = 2)

save_fig(fig_rq1, "results-rq1-warm-runtime", width = W_COL, height = 5.2)

message("[3b] RQ1: cold-pull distribution cost")

size_energy <- cells %>%
  filter(outcome == "cold_energy", treatment == "baseline") %>%
  select(subject, track, workload, energy_j = value) %>%
  inner_join(size_cells %>% filter(treatment == "baseline") %>% select(subject, size_mb),
             by = "subject")

rq1_corr <- {
  ct <- suppressWarnings(cor.test(size_energy$size_mb, size_energy$energy_j,
                                  method = "spearman", exact = FALSE))
  tibble(n = nrow(size_energy), rho = unname(ct$estimate), p_raw = ct$p.value)
}

size_energy_all <- cells %>%
  filter(outcome == "cold_energy") %>%
  select(subject, track, workload, treatment, energy_j = value) %>%
  inner_join(size_cells %>% select(subject, treatment, size_mb),
             by = c("subject", "treatment")) %>%
  mutate(treatment = treat_factor(as.character(treatment)))

message("    figure: cold-pull distribution cost")

cold_ids <- COLD_OUTCOMES$id
p_cold <- map(seq_along(cold_ids), function(i)
  panel_delta(cold_ids[i]) + theme(plot.title = element_text(size = BASE_SIZE, face = "bold")))

cold_layout <- "
AABB
#CC#
"
fig_rq1_cold <- wrap_plots(
  p_cold,
  design = cold_layout,
  axis_titles = "collect_y"
)

save_fig(fig_rq1_cold, "results-rq1-cold-pull", width = W_COL, height = 5.2 * 2 / 3)

message("    figure: cold-pull energy by subject")

cold_subject <- cold_long %>%
  filter(outcome == "cold_energy") %>%
  mutate(treatment = treat_factor(as.character(treatment)))

subj_order <- cold_subject %>%
  filter(treatment == "Baseline") %>%
  group_by(subject) %>%
  summarise(m = median(value), .groups = "drop") %>%
  arrange(m) %>%
  pull(subject)

cold_subject <- cold_subject %>% mutate(subject = factor(subject, levels = subj_order))

cold_subject_med <- cold_subject %>%
  group_by(subject, treatment) %>%
  summarise(m = median(value), .groups = "drop")

COLD_OFFSET <- setNames(c(-0.24, 0, 0.24), TREAT_LABELS[1:3])

place <- function(df) {
  df %>% mutate(xc = as.numeric(subject) + COLD_OFFSET[as.character(treatment)])
}

cold_subject <- place(cold_subject)
set.seed(20260821)
cold_subject$xj <- cold_subject$xc + runif(nrow(cold_subject), -0.055, 0.055)
cold_subject_med <- place(cold_subject_med)

missing_cold <- crossing(subject = factor(subj_order, levels = subj_order),
                         treatment = factor(TREAT_LABELS[2:3], levels = TREAT_LABELS)) %>%
  anti_join(cold_subject_med %>% select(subject, treatment), by = c("subject", "treatment")) %>%
  place() %>%
  mutate(y = min(cold_subject$value) * 0.62)

fig_rq1_cold_subjects <- ggplot(cold_subject, aes(x = xj, y = value, colour = treatment)) +
  geom_point(size = 0.5, alpha = 0.55, stroke = 0) +
  geom_segment(data = cold_subject_med, inherit.aes = FALSE,
               aes(x = xc - 0.105, xend = xc + 0.105, y = m, yend = m, colour = treatment),
               linewidth = 0.45, show.legend = FALSE) +
  geom_point(data = missing_cold, inherit.aes = FALSE,
             aes(x = xc, y = y, colour = treatment),
             shape = 4, size = 1.3, stroke = 0.6, show.legend = FALSE) +
  scale_x_continuous(breaks = seq_along(subj_order), labels = subj_order,
                     limits = c(0.4, length(subj_order) + 0.6), expand = c(0, 0)) +
  scale_y_log10(labels = label_number(big.mark = ",", accuracy = 1)) +
  scale_colour_manual(values = PAL_TREAT, name = NULL,
                      breaks = TREAT_LABELS[1:3], limits = TREAT_LABELS[1:3]) +
  labs(x = NULL, y = "Pull energy (J, log scale)") +
  theme(legend.position = "top",
        axis.text.x = element_text(angle = 30, hjust = 1),
        panel.grid.major.x = element_blank())

save_fig(fig_rq1_cold_subjects, "results-rq1-cold-pull-by-subject",
         width = W_FULL, height = 2.2)

message("    figure: image size against pull energy")

fig_rq1_size_energy <- ggplot(size_energy_all,
                              aes(x = size_mb, y = energy_j, colour = treatment)) +
  geom_point(size = 1.1, alpha = 0.9, stroke = 0) +
  ggrepel::geom_text_repel(
    data = size_energy %>% mutate(treatment = factor("Baseline", levels = TREAT_LABELS)),
    aes(label = subject), size = BASE_SIZE * 0.26, colour = "grey30",
    segment.size = 0.2, min.segment.length = 0.2, max.overlaps = 6,
    seed = 20260821, show.legend = FALSE) +
  scale_x_log10(labels = label_number(big.mark = ",", accuracy = 1)) +
  scale_y_log10(labels = label_number(big.mark = ",", accuracy = 1)) +
  scale_colour_manual(values = PAL_TREAT, name = NULL,
                      breaks = TREAT_LABELS[1:3], limits = TREAT_LABELS[1:3]) +
  annotation_logticks(sides = "bl", size = 0.2,
                      short = unit(1, "pt"), mid = unit(1.6, "pt"), long = unit(2.4, "pt")) +
  labs(x = "Image size (MB, log scale)", y = "Whole-node pull energy (J, log scale)") +
  theme(legend.position = "top")

save_fig(fig_rq1_size_energy, "results-rq1-size-energy", width = W_COL, height = 2.6)

message("[4] RQ1.1: warm runtime against cold pull")

PHASE_LEVELS <- c("Warm runtime", "Cold pull")

PHASE_MEASURES <- tribble(
  ~measure,   ~warm_id,        ~cold_id,        ~label,
  "energy",   "warm_energy",   "cold_energy",   "Energy",
  "duration", "warm_duration", "cold_duration", "Duration"
)

PHASE_TREATMENTS <- c("slim", "blafs")

phase_deltas <- map_dfr(seq_len(nrow(PHASE_MEASURES)), function(i) {
  m <- PHASE_MEASURES[i, ]
  deltas %>%
    filter(outcome %in% c(m$warm_id, m$cold_id)) %>%
    transmute(measure = m$measure, measure_label = m$label,
              track, subject, workload, stratum, treatment,
              phase = if_else(outcome == m$warm_id, PHASE_LEVELS[1], PHASE_LEVELS[2]),
              delta)
}) %>%
  mutate(phase = factor(phase, levels = PHASE_LEVELS),
         measure = factor(measure, levels = PHASE_MEASURES$measure))

phase_levels_summary <- phase_deltas %>%
  group_by(measure, measure_label, phase, treatment) %>%
  summarise(n_subjects = n_distinct(subject), median_delta = median(delta),
            .groups = "drop") %>%
  mutate(treatment = treat_factor(as.character(treatment)))

art_model <- function(df, measure_id, treatments = PHASE_TREATMENTS) {
  d <- df %>%
    filter(measure == measure_id, treatment %in% treatments) %>%
    mutate(treatment = factor(as.character(treatment), levels = treatments,
                              labels = TREAT_LABELS[match(treatments, TREAT_LEVELS)]),
           phase = factor(as.character(phase), levels = PHASE_LEVELS),
           subject = factor(subject))

  keep <- d %>% count(subject) %>%
    filter(n == length(treatments) * nlevels(d$phase)) %>% pull(subject)
  d <- d %>% filter(subject %in% keep) %>% mutate(subject = droplevels(subject))
  if (n_distinct(d$subject) < 3) return(NULL)
  m <- art(delta ~ treatment * phase + (1 | subject), data = d)
  list(model = m, data = d, n_subjects = n_distinct(d$subject))
}

art_table <- function(fit, model_label) {
  if (is.null(fit)) return(tibble())
  a <- anova(fit$model)
  tibble(
    model    = model_label,
    term     = as.character(a$Term),
    df_num   = a$Df,
    df_den   = a$Df.res,
    F        = a$F,
    p_raw    = a$`Pr(>F)`,
    n_subjects = fit$n_subjects
  )
}

art_diagnostics <- function(fit, model_label) {
  if (is.null(fit)) return(tibble())
  s <- summary(fit$model)
  aa <- s$aligned.anova
  tibble(
    model      = model_label,
    term       = as.character(aa$Term),
    aligned_by = as.character(aa$`Aligned By`),
    F_aligned  = as.numeric(aa$F)
  ) %>%
    mutate(
      max_col_sum  = max(abs(s$aligned.col.sums)),
      alignment_ok = F_aligned < 1e-6 & max_col_sum < 1e-6
    )
}

fit_energy   <- art_model(phase_deltas, "energy")
fit_duration <- art_model(phase_deltas, "duration")

rq11_art <- bind_rows(
  art_table(fit_energy,   "Energy"),
  art_table(fit_duration, "Duration")
) %>%
  group_by(model) %>%
  mutate(p_bh = bh(p_raw)) %>%
  ungroup()

rq11_art_diag <- bind_rows(
  art_diagnostics(fit_energy,   "Energy"),
  art_diagnostics(fit_duration, "Duration")
)

rq11_within <- phase_deltas %>%
  filter(treatment %in% PHASE_TREATMENTS) %>%
  group_by(measure, measure_label, phase) %>%
  group_modify(~ contrasts_for_outcome(.x, PHASE_TREATMENTS)) %>%
  ungroup() %>%
  mutate(contrast = as.character(contrast), phase = as.character(phase))

rq11_gap <- phase_deltas %>%
  filter(treatment %in% PHASE_TREATMENTS) %>%
  mutate(phase_key = if_else(phase == PHASE_LEVELS[1], "warm", "cold")) %>%
  select(measure, measure_label, subject, treatment, phase_key, delta) %>%
  pivot_wider(names_from = phase_key, values_from = delta) %>%
  filter(!is.na(warm), !is.na(cold)) %>%
  group_by(measure, measure_label, treatment) %>%
  group_modify(~ paired_contrast(setNames(.x$cold, .x$subject),
                                 setNames(.x$warm, .x$subject),
                                 "Cold pull", "Warm runtime")) %>%
  ungroup() %>%
  mutate(contrast = paste0(treat_factor(as.character(treatment)),
                           ": cold pull vs. warm runtime"),
         phase = "Between phases")

rq11_pairwise <- bind_rows(rq11_within, rq11_gap) %>%
  mutate(phase = factor(phase, levels = c(PHASE_LEVELS, "Between phases"))) %>%
  group_by(measure) %>%
  mutate(p_bh = bh(p_raw)) %>%
  ungroup() %>%
  arrange(measure, phase, contrast)

rq11_key <- list(
  n_subjects_energy   = if (is.null(fit_energy))   NA_integer_ else fit_energy$n_subjects,
  n_subjects_duration = if (is.null(fit_duration)) NA_integer_ else fit_duration$n_subjects,
  n_pairwise          = nrow(rq11_pairwise),
  n_sig_bh            = sum(rq11_pairwise$p_bh < ALPHA, na.rm = TRUE),
  min_p_bh            = suppressWarnings(min(rq11_pairwise$p_bh, na.rm = TRUE))
)

message("    figure: phase effects")

TREAT_PHASE_LABELS <- TREAT_LABELS[match(PHASE_TREATMENTS, TREAT_LEVELS)]

pd11 <- phase_deltas %>%
  filter(treatment %in% PHASE_TREATMENTS) %>%
  mutate(treatment = treat_factor(as.character(treatment)),
         panel = paste0(measure_label, " -- ", as.character(treatment)))

PANEL_ORDER <- unlist(lapply(PHASE_MEASURES$label, function(l)
  paste0(l, " -- ", TREAT_PHASE_LABELS)))
pd11$panel <- factor(pd11$panel, levels = PANEL_ORDER)

p11a <- ggplot(pd11, aes(x = phase, y = delta)) +
  geom_hline(yintercept = 0, linetype = "22", colour = "grey40", linewidth = 0.3) +
  geom_line(aes(group = subject), colour = "grey55", linewidth = 0.2, alpha = 0.7) +
  geom_point(aes(colour = treatment), size = 0.85, alpha = 0.9, stroke = 0,
             show.legend = FALSE) +
  stat_summary(fun = median, geom = "errorbar",
               aes(ymin = after_stat(y), ymax = after_stat(y)),
               width = 0.5, linewidth = 0.45, colour = "grey15") +
  facet_wrap(~ panel, ncol = 2) +
  scale_x_discrete(limits = PHASE_LEVELS,
                   labels = c("Warm runtime" = "Warm\nruntime",
                              "Cold pull" = "Cold\npull")) +
  scale_colour_manual(values = PAL_TREAT, guide = "none") +
  labs(x = NULL, y = "Change from baseline (%)")

fig_rq11 <- p11a

save_fig(fig_rq11, "results-rq11-phase-effects", width = W_COL, height = 3.8)

message("[5] RQ1.2: workload types")

subject_coverage <- warm_meta %>%
  group_by(workload, subject, treatment) %>%
  summarise(any_correct = any(correct), .groups = "drop")

rq12_estimability <- subject_coverage %>%
  group_by(workload, treatment) %>%
  summarise(n_subjects = n(), n_covered = sum(any_correct), .groups = "drop") %>%
  mutate(workload = factor(workload, levels = WORKLOAD_LEVELS),
         treatment = treat_factor(as.character(treatment)),
         estimable = n_covered > 0) %>%
  arrange(workload, treatment)

rq12_empty_cells <- rq12_estimability %>% filter(!estimable)

WORKLOAD_FACTOR <- WORKLOAD_LEVELS[1:4]
MIN_CELL <- 2L

art_workload <- function(o_id, treatments) {
  d <- deltas %>%
    filter(outcome == o_id, treatment %in% treatments,
           workload %in% WORKLOAD_FACTOR) %>%
    mutate(treatment = factor(as.character(treatment), levels = treatments,
                              labels = TREAT_LABELS[match(treatments, TREAT_LEVELS)]),
           workload = factor(workload, levels = WORKLOAD_FACTOR),
           subject = factor(subject))
  keep <- d %>% count(subject) %>% filter(n == length(treatments)) %>% pull(subject)
  d <- d %>% filter(subject %in% keep) %>% mutate(subject = droplevels(subject))
  tab <- table(d$workload, d$treatment)
  ok <- nrow(d) > 0 && all(tab >= MIN_CELL)
  empty_cells <- sum(tab == 0)
  thin_cells  <- sum(tab > 0 & tab < MIN_CELL)
  if (!ok) {
    return(tibble(outcome = o_id,
                  term = c("treatment", "workload", "treatment:workload"),
                  df_num = NA_real_, df_den = NA_real_, F = NA_real_,
                  p_raw = NA_real_, n_subjects = n_distinct(d$subject),
                  empty_cells = empty_cells, thin_cells = thin_cells,
                  estimable = FALSE))
  }
  m <- art(delta ~ treatment * workload + (1 | subject), data = d)
  a <- anova(m)
  tibble(outcome = o_id, term = as.character(a$Term), df_num = a$Df,
         df_den = a$Df.res, F = a$F, p_raw = a$`Pr(>F)`,
         n_subjects = n_distinct(d$subject), empty_cells = empty_cells,
         thin_cells = thin_cells, estimable = TRUE)
}

rq12_art <- bind_rows(
  map_dfr(WARM_OUTCOMES, art_workload, treatments = DEBLOATERS) %>%
    mutate(model = "Three debloaters"),
  map_dfr(WARM_OUTCOMES, art_workload,
          treatments = c("blafs", "confine")) %>%
    mutate(model = "BLAFS and Confine"),
  map_dfr(COLD_OUTCOMES$id, art_workload,
          treatments = c("slim", "blafs")) %>%
    mutate(model = "SlimToolkit and BLAFS, cold pull")
) %>%
  group_by(model, term) %>%
  mutate(p_bh = bh(p_raw)) %>%
  ungroup()

rq12_key <- list(
  n_models          = nrow(rq12_art) / 3,
  n_estimable       = sum(rq12_art$estimable) / 3,
  min_cell          = MIN_CELL
)

rq12_pairwise <- deltas %>%
  mutate(workload = factor(workload, levels = WORKLOAD_LEVELS)) %>%
  group_by(outcome, workload) %>%
  group_modify(~ contrasts_for_outcome(
    .x, intersect(DEBLOATERS, outcome_treatments(.y$outcome)))) %>%
  ungroup() %>%
  filter(b == "Baseline") %>%          
  group_by(outcome) %>%
  mutate(p_bh = bh(p_raw)) %>%
  ungroup()

rq12_pairwise_key <- list(
  planned  = nrow(rq12_pairwise),
  testable = sum(!is.na(rq12_pairwise$p_raw)),
  min_bh   = suppressWarnings(min(rq12_pairwise$p_bh, na.rm = TRUE)),
  widest   = rq12_pairwise %>% filter(!is.na(p_raw)) %>% slice_min(p_raw, n = 2)
)

cliffs_delta <- function(x, y) {
  if (!length(x) || !length(y)) return(NA_real_)
  mean(outer(x, y, ">") ) - mean(outer(x, y, "<"))
}

rq12_stack <- deltas %>%
  group_by(outcome, treatment) %>%
  group_modify(function(d, k) {
    x <- d$delta[d$track == "single"]
    y <- d$delta[d$track == "stack"]
    if (length(x) < 2 || length(y) < 2) {
      return(tibble(n_single = length(x), n_stack = length(y), U = NA_real_,
                    p_raw = NA_real_, cliff = NA_real_, testable = FALSE))
    }
    w <- suppressWarnings(wilcox.test(x, y, exact = TRUE))
    tibble(n_single = length(x), n_stack = length(y), U = unname(w$statistic),
           p_raw = w$p.value, cliff = cliffs_delta(x, y), testable = TRUE)
  }) %>%
  ungroup() %>%
  mutate(p_bh = bh(p_raw), treatment = treat_factor(as.character(treatment)))

rq12_stack_key <- list(
  planned  = nrow(rq12_stack),
  testable = sum(rq12_stack$testable),
  min_bh   = suppressWarnings(min(rq12_stack$p_bh, na.rm = TRUE))
)

message("    figure: workload effects")

FIG12_OUTCOMES <- c("warm_energy", "warm_duration", "cpu",
                    "cold_energy", "cold_duration", "cold_intensity")

TREAT_OFFSET <- setNames(c(-0.235, 0, 0.235), TREAT_LABELS[-1])
TREAT_OFFSET_COLD <- setNames(c(-0.13, 0.13), TREAT_LABELS[2:3])
WORKLOAD_SHORT <- c("General", "Serverless", "Machine\nlearning",
                    "Data\nintensive", "App.\nstack")
JIT_W <- 0.055

panel_workload <- function(o_id, show_x = TRUE) {
  o <- OUTCOMES %>% filter(id == o_id)
  is_cold <- o$campaign == "cold"
  treats  <- if (is_cold) TREAT_LABELS[2:3] else TREAT_LABELS[-1]
  offs    <- if (is_cold) TREAT_OFFSET_COLD else TREAT_OFFSET
  d <- deltas %>%
    filter(outcome == o_id) %>%
    mutate(treatment = as.character(treat_factor(as.character(treatment))),
           workload  = factor(workload, levels = WORKLOAD_LEVELS),
           xc = as.numeric(workload) + offs[treatment],

           treatment = factor(treatment, levels = TREAT_LABELS[-1]))
  set.seed(20260821)
  d$xj <- d$xc + runif(nrow(d), -JIT_W, JIT_W)

  meds <- d %>%
    group_by(workload, treatment, xc) %>%
    summarise(n = n(), med = median(delta), .groups = "drop") %>%
    filter(n >= CROSSBAR_MIN)

  rng <- range(d$delta)
  span <- diff(rng)

  empty <- tidyr::expand_grid(
      workload  = factor(WORKLOAD_LEVELS, levels = WORKLOAD_LEVELS),
      treatment = factor(treats, levels = TREAT_LABELS[-1])) %>%
    anti_join(distinct(d, workload, treatment), by = c("workload", "treatment")) %>%
    mutate(xc = as.numeric(workload) + offs[as.character(treatment)],
           y  = rng[1] - 0.11 * span)

  ylab <- if (o$norm == "pct") "Change from baseline (%)"
          else paste0("Change from baseline (", o$unit, ")")

  ggplot(d, aes(x = xj, y = delta, colour = treatment)) +
    geom_hline(yintercept = 0, linetype = "22", colour = "grey40", linewidth = 0.3) +
    geom_vline(xintercept = seq(1.5, length(WORKLOAD_LEVELS) - 0.5, by = 1),
               colour = "grey88", linewidth = 0.3) +
    geom_segment(data = meds, inherit.aes = FALSE,
                 aes(x = xc - 0.105, xend = xc + 0.105, y = med, yend = med,
                     colour = treatment),
                 linewidth = 0.5, show.legend = FALSE) +
    geom_point(size = 0.9, alpha = 0.92, stroke = 0) +
    geom_point(data = empty, inherit.aes = FALSE,
               aes(x = xc, y = y, colour = treatment),
               shape = 4, size = 1.4, stroke = 0.65, show.legend = FALSE) +
    scale_x_continuous(breaks = seq_along(WORKLOAD_LEVELS),
                       labels = WORKLOAD_SHORT,
                       limits = c(0.5, length(WORKLOAD_LEVELS) + 0.5),
                       expand = c(0, 0)) +
    scale_colour_manual(values = PAL_TREAT, breaks = TREAT_LABELS[-1],
                        limits = TREAT_LABELS[-1], name = NULL, drop = FALSE) +
    labs(title = o$label, x = NULL, y = ylab) +

    (if (is_cold) guides(colour = "none") else NULL) +
    theme(panel.grid.major.x = element_blank(),
          axis.text.x = if (show_x) element_text(size = BASE_SIZE - 2, lineheight = 0.88)
                        else element_blank())
}

p12 <- map2(FIG12_OUTCOMES,
            seq_along(FIG12_OUTCOMES) > length(FIG12_OUTCOMES) - 3L,
            panel_workload)

fig_rq12 <- wrap_plots(p12, ncol = 3) +
  plot_layout(guides = "collect") &
  theme(legend.position = "bottom")

save_fig(fig_rq12, "results-rq12-workload-effects", width = W_FULL, height = 4.0)

message("[6] RQ1.3: debloating paradigms")

PARADIGM_LEVELS <- c("File removal", "System-call restriction")

paradigm_deltas <- deltas %>%
  filter(outcome %in% WARM_OUTCOMES) %>%
  mutate(paradigm = if_else(treatment == "confine",
                            "System-call restriction", "File removal")) %>%
  group_by(outcome, track, subject, workload, paradigm) %>%
  summarise(delta = median(delta), n_tools = n(), .groups = "drop") %>%
  mutate(paradigm = factor(paradigm, levels = PARADIGM_LEVELS))

rq13_tests <- paradigm_deltas %>%
  group_by(outcome) %>%
  group_modify(function(d, k) {
    w <- d %>% select(subject, paradigm, delta) %>%
      pivot_wider(names_from = paradigm, values_from = delta)
    fr <- setNames(w$`File removal`, w$subject)
    sr <- setNames(w$`System-call restriction`, w$subject)
    paired_contrast(fr, sr, "File removal", "System-call restriction")
  }) %>%
  ungroup() %>%
  mutate(p_bh = bh(p_raw)) %>%
  left_join(OUTCOMES %>% select(id, label, unit, norm), by = c("outcome" = "id")) %>%
  arrange(match(outcome, OUTCOMES$id))

size_tests <- {
  w <- size_deltas %>%
    select(subject, treatment, delta) %>%
    pivot_wider(names_from = treatment, values_from = delta)
  vec <- function(t) if (t %in% names(w)) setNames(w[[t]], w$subject)
                     else setNames(numeric(0), character(0))
  bind_rows(
    paired_contrast(vec("slim"),  NULL, "SlimToolkit", "Baseline"),
    paired_contrast(vec("blafs"), NULL, "BLAFS", "Baseline"),
    paired_contrast(vec("slim"), vec("blafs"), "SlimToolkit", "BLAFS")
  ) %>%
    mutate(p_bh = bh(p_raw))
}

size_normality <- bind_rows(
  size_deltas %>% group_by(treatment) %>%
    group_modify(~ shapiro_safe(.x$delta)) %>% ungroup() %>%
    mutate(contrast = paste(treat_factor(as.character(treatment)), "vs. Baseline")) %>%
    select(contrast, n, W, p, testable, rejects),
  {
    w <- size_deltas %>% select(subject, treatment, delta) %>%
      pivot_wider(names_from = treatment, values_from = delta) %>%
      filter(!is.na(slim), !is.na(blafs))
    shapiro_safe(w$slim - w$blafs) %>%
      transmute(contrast = "SlimToolkit vs. BLAFS", n, W, p, testable, rejects)
  }
)

size_descriptives <- size_deltas %>%
  group_by(treatment) %>%
  group_modify(~ describe6(.x$delta)) %>%
  ungroup() %>%
  mutate(treatment = treat_factor(as.character(treatment)))

size_common <- size_deltas %>%
  select(subject, treatment, delta) %>%
  pivot_wider(names_from = treatment, values_from = delta) %>%
  filter(!is.na(slim), !is.na(blafs))

size_all_variants <- cold_trials %>%
  filter(!is.na(size_mb)) %>%
  group_by(subject, treatment) %>%
  summarise(size_mb = median(size_mb), .groups = "drop") %>%
  group_by(subject) %>%
  filter(any(treatment == "baseline")) %>%
  mutate(base = size_mb[treatment == "baseline"]) %>%
  ungroup() %>%
  filter(treatment != "baseline") %>%
  mutate(delta = 100 * (size_mb - base) / base) %>%
  left_join(variant_correct, by = c("subject", "treatment"))

size_inversions <- size_all_variants %>% filter(delta > 0) %>% arrange(desc(delta))

rq13_size_key <- list(
  n_slim         = sum(size_deltas$treatment == "slim"),
  n_blafs        = sum(size_deltas$treatment == "blafs"),
  n_common       = nrow(size_common),
  median_slim    = median(size_deltas$delta[size_deltas$treatment == "slim"]),
  median_blafs   = median(size_deltas$delta[size_deltas$treatment == "blafs"]),
  n_inversions   = nrow(size_inversions),
  n_inv_correct  = sum(size_inversions$any_correct)
)

profile_files <- list.files(file.path("replication", "debloat", "confine_profiles"),
                            pattern = "\\.gl1\\.seccomp\\.json$", full.names = TRUE)

read_blocked <- function(path) {
  txt <- paste(readLines(path, warn = FALSE), collapse = "")
  subject <- sub("\\.gl1\\.seccomp\\.json$", "", basename(path))

  blocks <- strsplit(txt, '\\{"names":')[[1]][-1]
  n <- sum(vapply(blocks, function(b) {
    if (!grepl("SCMP_ACT_ERRNO", b)) return(0L)
    names_part <- sub('^\\s*\\[(.*?)\\].*$', '\\1', b)
    length(strsplit(names_part, ",")[[1]])
  }, integer(1)))
  mode_file <- file.path(dirname(path), paste0(subject, ".mode"))
  tibble(subject = subject,
         blocked = n,
         mode = if (file.exists(mode_file)) readLines(mode_file, warn = FALSE)[1] else NA_character_)
}

blocked_calls <- map_dfr(profile_files, read_blocked) %>%
  mutate(mode = recode(mode, "static" = "Static", "dynamic" = "Dynamic"),
         mode = factor(mode, levels = c("Dynamic", "Static"))) %>%
  arrange(desc(blocked))

rq13_key <- list(
  n_profiles   = nrow(blocked_calls),
  min_blocked  = min(blocked_calls$blocked),
  max_blocked  = max(blocked_calls$blocked),
  med_blocked  = median(blocked_calls$blocked),
  n_static     = sum(blocked_calls$mode == "Static"),
  n_dynamic    = sum(blocked_calls$mode == "Dynamic"),
  no_profile   = setdiff(subject_meta$subject[subject_meta$track == "single"],
                         blocked_calls$subject)
)

message("    figure: paradigm mechanisms")

PAL_MODE <- c("Dynamic" = "#00674F", "Static" = "#66C2A5")

bc <- blocked_calls %>% mutate(subject = fct_reorder(subject, blocked))

p13a <- ggplot(bc, aes(x = blocked, y = subject, fill = mode)) +
  geom_col(width = 0.72) +
  geom_text(aes(label = blocked), hjust = -0.22, size = BASE_SIZE * 0.30,
            colour = "grey20") +
  scale_fill_manual(values = PAL_MODE, name = "Profile generation") +
  scale_x_continuous(expand = expansion(mult = c(0, 0.14))) +
  labs(title = "(a) System calls denied by the generated profile",
       x = "Blocked system calls (count)", y = NULL) +
  theme(legend.position = "bottom", panel.grid.major.y = element_blank(),
        panel.grid.major.x = element_line(linewidth = 0.25, colour = "grey88"))

pd13 <- paradigm_deltas %>%
  filter(outcome %in% c("warm_energy", "warm_duration", "warm_power", "cpu")) %>%
  mutate(outcome = factor(outcome,
                          levels = c("warm_energy", "warm_duration", "warm_power", "cpu"),
                          labels = c("Warm-runtime\nenergy (%)",
                                     "Warm-runtime\nduration (%)",
                                     "Warm-runtime\npower (W)",
                                     "CPU utilization\n(pp)")))

p13b <- ggplot(pd13, aes(x = paradigm, y = delta)) +
  geom_hline(yintercept = 0, linetype = "22", colour = "grey40", linewidth = 0.3) +
  dist_layers(pd13, xvar = "paradigm", fillvar = "paradigm", labels_below = 0, panelvars = "outcome") +
  facet_wrap(~ outcome, nrow = 1, scales = "free_y") +
  scale_x_discrete(limits = PARADIGM_LEVELS,
                   labels = c("File removal" = "File\nremoval",
                              "System-call restriction" = "System-call\nrestriction")) +
  scale_fill_manual(values = PAL_PARADIGM, guide = "none") +
  scale_colour_manual(values = PAL_PARADIGM, guide = "none") +
  labs(title = "(b) Warm-runtime change from baseline, aggregated to the paradigm",
       x = NULL, y = "Change from baseline (unit in panel heading)")

sz <- size_all_variants %>%
  mutate(treatment = treat_factor(as.character(treatment)),
         subject = fct_reorder(subject, delta),
         gated = if_else(any_correct, "Correct variant", "Fails the correctness gate"))

p13c <- ggplot(sz, aes(x = delta, y = subject, fill = treatment, alpha = gated)) +
  geom_col(width = 0.7, position = position_dodge(width = 0.75, preserve = "single")) +
  geom_vline(xintercept = 0, colour = "grey30", linewidth = 0.35) +
  scale_fill_manual(values = PAL_TREAT, name = NULL,
                    breaks = TREAT_LABELS[2:3], limits = TREAT_LABELS[2:3]) +
  scale_alpha_manual(values = c("Correct variant" = 1, "Fails the correctness gate" = 0.30),
                     name = NULL, labels = c("Correct", "Not correct")) +
  geom_text(data = sz %>% filter(delta > 100),
            aes(x = 100, y = subject, label = paste0("+", formatC(delta, format = "f", digits = 0,
                                                     big.mark = ","), " %")),
            hjust = 1.06, size = BASE_SIZE * 0.28, colour = "grey20",
            inherit.aes = FALSE, position = position_nudge(y = 0.18)) +
  scale_x_continuous(labels = label_number(suffix = "%"),
                     limits = c(-100, 100), oob = scales::oob_squish,
                     expand = expansion(mult = 0.01)) +
  labs(title = "(c) Change in image size", x = "Change from baseline (%)", y = NULL) +
  theme(legend.position = "bottom", legend.box = "vertical",
        legend.spacing.y = unit(1, "pt"),
        panel.grid.major.y = element_blank(),
        panel.grid.major.x = element_line(linewidth = 0.25, colour = "grey88")) +
  guides(fill = guide_legend(order = 1), alpha = guide_legend(order = 2))

fig_rq13 <- (p13a | p13c) / p13b + plot_layout(heights = c(1.55, 1))

save_fig(fig_rq13, "results-rq13-mechanisms", width = W_FULL, height = 4.8)

message("[7] RQ2: functional reliability")

correctness_cells <- warm_meta %>%
  group_by(track, subject, workload, treatment) %>%
  summarise(n_trials = n(), n_correct = sum(correct), .groups = "drop") %>%
  mutate(rate = 100 * n_correct / n_trials,
         fail_rate = 100 - rate,
         treatment = treat_factor(as.character(treatment)),
         workload = factor(workload, levels = WORKLOAD_LEVELS))

rq2_by_treatment <- warm_meta %>%
  group_by(treatment) %>%
  summarise(n_trials = n(), n_correct = sum(correct), .groups = "drop") %>%
  mutate(fail_rate = 100 * (n_trials - n_correct) / n_trials,
         treatment = treat_factor(as.character(treatment)))

rq2_descriptives <- correctness_cells %>%
  group_by(treatment) %>%
  group_modify(~ describe6(.x$rate)) %>%
  ungroup()

rq2_nondeterministic <- correctness_cells %>%
  filter(n_correct > 0, n_correct < n_trials)

rq2_omnibus <- correctness_cells %>%
  transmute(subject, treatment = factor(as.character(treatment), levels = TREAT_LABELS),
            value = rate) %>%
  { m <- pivot_wider(., names_from = treatment, values_from = value) %>%
        column_to_rownames("subject") %>% as.matrix()
    ft <- friedman.test(m)
    tibble(chi2 = unname(ft$statistic), df = unname(ft$parameter),
           n_blocks = nrow(m), p_raw = ft$p.value) }

rq2_pairwise <- {
  w <- correctness_cells %>%
    select(subject, treatment, rate) %>%
    pivot_wider(names_from = treatment, values_from = rate)
  vec <- function(t) setNames(w[[t]], w$subject)
  pairs <- combn(TREAT_LABELS, 2, simplify = FALSE)
  map_dfr(pairs, function(p) paired_contrast(vec(p[1]), vec(p[2]), p[1], p[2]))
}

rq2_tests <- bind_rows(
  rq2_omnibus %>% transmute(kind = "omnibus", contrast = "Friedman (4 treatments)",
                            n_pairs = n_blocks, n_nonzero = NA_integer_,
                            statistic = chi2, df, p_raw,
                            median_diff = NA_real_, r_rb = NA_real_,
                            magnitude = NA_character_),
  rq2_pairwise %>% transmute(kind = "pairwise", contrast = as.character(contrast),
                             n_pairs, n_nonzero, statistic = NA_real_, df = NA_real_,
                             p_raw, median_diff, r_rb, magnitude)
) %>%
  mutate(p_bh = bh(p_raw))

FAIL_STAGES <- c("Build failure", "Start failure", "Workload failure",
                 "Output mismatch")

rq2_stages <- warm_meta %>%
  filter(!correct) %>%
  count(treatment, fail_stage, name = "n") %>%
  mutate(treatment = treat_factor(as.character(treatment)),
         fail_stage = factor(fail_stage, levels = FAIL_STAGES)) %>%

  complete(treatment = factor(TREAT_LABELS, levels = TREAT_LABELS),
           fail_stage = factor(FAIL_STAGES, levels = FAIL_STAGES),
           fill = list(n = 0L)) %>%
  group_by(treatment) %>%
  mutate(pct = if (sum(n) > 0) 100 * n / sum(n) else n * 0) %>%
  ungroup()

rq2_key <- list(
  n_trials      = nrow(warm_meta),
  n_failures    = sum(!warm_meta$correct),
  n_mismatch    = sum(warm_meta$fail_stage == "Output mismatch", na.rm = TRUE),
  n_nondet      = nrow(rq2_nondeterministic),
  fail_rates    = setNames(rq2_by_treatment$fail_rate, as.character(rq2_by_treatment$treatment)),
  n_all_or_none = sum(correctness_cells$n_correct %in% c(0L, 20L))
)

message("    figure: correctness matrix")

PAL_SEQ_FN <- colorRampPalette(c("#F4A582", "#FDDBC7", "#D1E5F0", "#4393C3", "#1B4F72"))

cc <- correctness_cells %>%
  arrange(workload, desc(subject)) %>%
  mutate(subject = factor(subject, levels = unique(subject)))

p2a <- ggplot(cc, aes(x = treatment, y = subject, fill = rate)) +
  geom_tile(colour = "white", linewidth = 0.6) +
  geom_text(aes(label = n_correct,
                colour = rate > 55, fontface = if_else(n_correct == 0, "bold", "plain")),
            size = BASE_SIZE * 0.32, show.legend = FALSE) +
  scale_fill_gradientn(colours = PAL_SEQ_FN(64), limits = c(0, 100),
                       name = "Correct trials (%)",
                       guide = guide_colourbar(barheight = unit(4, "pt"),
                                               barwidth = unit(52, "pt"),
                                               title.position = "top")) +
  scale_colour_manual(values = c(`TRUE` = "white", `FALSE` = "grey15")) +
  scale_x_discrete(position = "top") +
  facet_grid(workload ~ ., scales = "free_y", space = "free_y", switch = "y") +
  labs(title = "(a) Correct trials per subject and treatment (of 20)",
       x = NULL, y = NULL) +
  theme(panel.grid = element_blank(),
        legend.position = "bottom",
        panel.spacing.y = unit(2.5, "pt"),
        strip.placement = "outside",
        strip.text.y.left = element_text(angle = 0, hjust = 1, size = BASE_SIZE - 0.5),
        axis.text.x = element_text(angle = 22, hjust = 0),
        axis.ticks = element_blank())

p2b <- ggplot(rq2_stages, aes(x = treatment, y = n, fill = fail_stage)) +
  geom_col(width = 0.66, colour = "white", linewidth = 0.3) +
  geom_text(data = rq2_stages %>% filter(n > 0),
            aes(label = n), position = position_stack(vjust = 0.5),
            size = BASE_SIZE * 0.30, colour = "white") +
  geom_text(data = rq2_stages %>% group_by(treatment) %>%
                     summarise(n = sum(n), .groups = "drop"),
            aes(x = treatment, y = n, label = n), inherit.aes = FALSE,
            vjust = -0.55, size = BASE_SIZE * 0.32, colour = "grey15") +
  scale_y_continuous(expand = expansion(mult = c(0, 0.10))) +
  scale_fill_manual(values = c("Build failure" = "#3D3D3D",
                               "Start failure" = "#D55E00",
                               "Workload failure" = "#0072B2",
                               "Output mismatch" = "#CC79A7"),
                    drop = FALSE, name = NULL) +
  labs(title = "(b) Failures by stage", x = NULL, y = "Failed trials (count)") +
  theme(legend.position = "bottom", axis.text.x = element_text(angle = 22, hjust = 1)) +
  guides(fill = guide_legend(ncol = 2, byrow = TRUE))

fig_rq2 <- p2a + p2b + plot_layout(widths = c(1.15, 1))

save_fig(fig_rq2, "results-rq2-correctness", width = W_FULL, height = 3.6)

message("[8] tables and key numbers")

tex_escape <- function(x) {
  x <- as.character(x)
  x <- gsub("\\\\", "\\\\textbackslash{}", x)
  x <- gsub("([&%$#_{}])", "\\\\\\1", x)
  x
}

fmt_p <- function(p) {
  vapply(p, function(v) {
    if (is.na(v)) return("--")
    if (v < 1e-3) {
      e <- floor(log10(v))
      m <- v / 10^e
      return(sprintf("$%.1f\\times10^{%d}$", m, e))
    }
    sub("^0", "", sprintf("%.3f", v))
  }, character(1))
}

fmt_f <- function(x, digits = 2, big = TRUE) {
  vapply(seq_along(x), function(i) {
    if (is.na(x[i])) return("--")
    formatC(x[i], format = "f", digits = digits, big.mark = if (big) "," else "")
  }, character(1))
}

fmt_sig <- function(x, digits = 3) {
  vapply(seq_along(x), function(i) {
    if (is.na(x[i]) || x[i] == 0) return("--")
    d <- if (abs(x[i]) < 0.1)
      max(2L, as.integer(digits - 1 - floor(log10(abs(x[i]))))) else 2L
    d <- min(d, 6L)
    formatC(x[i], format = "f", digits = d, big.mark = ",")
  }, character(1))
}

fmt_signed <- function(x, digits = 2) {
  vapply(seq_along(x), function(i) {
    if (is.na(x[i])) return("--")
    sprintf("%s%s", if (x[i] > 0) "+" else "", formatC(x[i], format = "f", digits = digits))
  }, character(1))
}

write_one_table <- function(df, path, align, header, groups) {
  con <- file(path, open = "wt", encoding = "UTF-8")
  on.exit(close(con))
  nc <- ncol(df)
  writeLines(sprintf("\\begin{tabular}{@{}%s@{}}", align), con)
  writeLines("\\toprule", con)
  writeLines(paste0(paste(header, collapse = " & "), " \\\\"), con)
  writeLines("\\midrule", con)
  last <- NULL
  for (i in seq_len(nrow(df))) {
    if (!is.null(groups)) {
      g <- groups[i]
      if (is.null(last) || g != last) {
        if (!is.null(last)) writeLines("\\addlinespace[2pt]", con)
        writeLines(sprintf("\\multicolumn{%d}{@{}l}{\\textit{%s}} \\\\", nc, g), con)
        last <- g
      }
    }
    writeLines(paste0(paste(as.character(unlist(df[i, ])), collapse = " & "), " \\\\"), con)
  }
  writeLines("\\bottomrule", con)
  writeLines("\\end{tabular}", con)
  message("  table:  ", path, "  (", nrow(df), " rows)")
}

write_table <- function(df, file, align, header, groups = NULL, max_rows = Inf) {
  stem <- sub("\\.tex$", "", file)
  if (nrow(df) <= max_rows || is.null(groups)) {
    write_one_table(df, file.path(DIR_TAB, file), align, header, groups)
    return(invisible(1L))
  }
  g <- as.character(groups)
  runs <- rle(g)
  part <- integer(0); cur <- 1L; used <- 0L
  for (k in seq_along(runs$lengths)) {
    if (used > 0 && used + runs$lengths[k] > max_rows) { cur <- cur + 1L; used <- 0L }
    part <- c(part, rep(cur, runs$lengths[k])); used <- used + runs$lengths[k]
  }
  for (k in unique(part)) {
    idx <- which(part == k)
    write_one_table(df[idx, , drop = FALSE],
                    file.path(DIR_TAB, sprintf("%s-%d.tex", stem, k)),
                    align, header, g[idx])
  }
  invisible(length(unique(part)))
}

outcome_label <- function(id) {
  lab <- OUTCOMES$label[match(id, OUTCOMES$id)]
  unit <- OUTCOMES$unit[match(id, OUTCOMES$id)]
  norm <- OUTCOMES$norm[match(id, OUTCOMES$id)]
  paste0(lab, " (", if_else(norm == "pct", "\\%", unit), ")")
}

pop <- correctness_cells %>%
  group_by(treatment) %>%
  summarise(subjects = n(), covered = sum(n_correct > 0),
            trials = sum(n_trials), correct = sum(n_correct), .groups = "drop") %>%
  mutate(rate = 100 * correct / trials)

tab_population <- pop %>%
  transmute(
    Treatment = tex_escape(as.character(treatment)),
    Trials    = formatC(trials, big.mark = ",", format = "d"),
    Correct   = formatC(correct, big.mark = ",", format = "d"),
    `Correct (\\%)` = fmt_f(rate, 1),
    `Subjects with a correct variant` = sprintf("%d / %d", covered, subjects)
  )

write_table(tab_population, "tab-population.tex",
            align = "lrrrr",
            header = c("Treatment", "Trials", "Correct", "Correct (\\%)",
                       "Subjects covered"))

tab_effect_summary <- rq1_descriptives %>%
  bind_rows(size_descriptives %>% mutate(outcome = "image_size")) %>%
  transmute(
    group = if_else(outcome == "image_size", "Image size (\\%)", outcome_label(outcome)),
    Treatment = tex_escape(as.character(treatment)),
    n = as.character(n),
    Mean = fmt_f(mean), Median = fmt_f(median), SD = fmt_f(sd),
    Min = fmt_f(min), Max = fmt_f(max), Variance = fmt_f(variance)
  )

write_table(tab_effect_summary %>% select(-group), "tab-effect-summary.tex",
            align = "lrrrrrrr",
            header = c("Treatment", "$n$", "Mean", "Median", "SD", "Min", "Max",
                       "Variance"),
            groups = tab_effect_summary$group)

tab_baseline <- rq1_baseline_levels %>%
  arrange(match(outcome, OUTCOMES$id)) %>%
  transmute(
    Outcome = outcome_label(outcome) %>% sub(" \\(.*\\)$", "", .) %>% tex_escape(),
    Unit = tex_escape(unit),
    n = as.character(n),
    Median = fmt_sig(median),
    Minimum = sprintf("%s (%s)", fmt_sig(min), tex_escape(min_subject)),
    Maximum = sprintf("%s (%s)", fmt_sig(max), tex_escape(max_subject))
  )

write_table(tab_baseline, "tab-rq1-baseline-levels.tex",
            align = "llrrll",
            header = c("Outcome", "Unit", "$n$", "Median", "Minimum (subject)",
                       "Maximum (subject)"))

tab_cold_verify <- cold_verify %>%
  transmute(
    Band = as.character(band),
    n = formatC(n, big.mark = ",", format = "d"),
    `Raw / recorded` = fmt_f(median_ratio, 3),
    `Raw power` = fmt_f(median_power_raw, 1),
    `Recorded power` = fmt_f(median_power_recorded, 1)
  )

write_table(tab_cold_verify, "tab-cold-verification.tex",
            align = "lrrrr",
            header = c("Pull duration", "Trials", "Raw / recorded energy",
                       "Raw power (W)", "Recorded power (W)"))

tab_normality <- rq1_normality %>%
  transmute(
    group = outcome_label(outcome),
    Contrast = tex_escape(contrast),
    n = as.character(n),
    W = fmt_f(W, 3),
    p = fmt_p(p),
    Normality = case_when(!testable ~ "not testable",
                          rejects ~ "rejected",
                          TRUE ~ "not rejected")
  )

write_table(tab_normality %>% select(-group), "tab-normality.tex",
            align = "lrrrl",
            header = c("Contrast", "$n$", "$W$", "$p$", "Normality at $\\alpha=.05$"),
            groups = tab_normality$group, max_rows = 40)

tab_rq1_omnibus <- rq1_omnibus %>%
  left_join(rq1_omnibus_restricted %>%
              select(outcome, chi2_r = chi2, n_r = n_blocks, p_r = p_raw),
            by = "outcome") %>%
  left_join(rq1_tests %>% filter(kind == "omnibus") %>% select(outcome, p_bh),
            by = "outcome") %>%
  arrange(match(outcome, OUTCOMES$id)) %>%
  transmute(
    Outcome = outcome_label(outcome),
    `$\\chi_F^2$` = fmt_f(chi2, 2),
    df = if_else(is.na(chi2), "--", as.character(df)),
    `$n$` = as.character(n_blocks),
    `$p$` = fmt_p(p_raw),
    `$p_{BH}$` = fmt_p(p_bh),
    `$\\chi_F^2$ ` = fmt_f(chi2_r, 2),
    `$n$ ` = as.character(n_r),
    `$p$ ` = fmt_p(p_r)
  )

write_table(tab_rq1_omnibus, "tab-rq1-omnibus.tex",
            align = "lrrrrrrrr",
            header = c("Outcome", "$\\chi_F^2$", "$df$", "$n$", "$p$", "$p_{BH}$",
                       "$\\chi_F^2$", "$n$", "$p$"))

tab_rq1_pairwise <- rq1_tests %>%
  filter(kind == "pairwise") %>%
  arrange(match(outcome, OUTCOMES$id)) %>%
  transmute(
    group = outcome_label(outcome),
    Contrast = tex_escape(contrast),
    n = as.character(n_pairs),
    nd = as.character(n_nonzero),
    `Median` = fmt_signed(median_diff),
    p = fmt_p(p_raw),
    pbh = fmt_p(p_bh),
    r = if_else(is.na(r_rb), "--", fmt_signed(r_rb)),
    Magnitude = if_else(is.na(magnitude), "--", magnitude)
  )

write_table(tab_rq1_pairwise %>% select(-group), "tab-rq1-pairwise.tex",
            align = "lrrrrrrl",
            header = c("Contrast", "$n$", "$n_{\\neq}$", "Median difference",
                       "$p$", "$p_{BH}$", "$r_{rb}$", "Magnitude"),
            groups = tab_rq1_pairwise$group, max_rows = 40)

tab_rq11_art <- rq11_art %>%
  transmute(
    group = model,
    Term = recode(term, "treatment" = "Debloating treatment", "phase" = "Runtime phase",
                  "treatment:phase" = "Treatment $\\times$ phase"),
    df = sprintf("%d, %s", df_num, fmt_f(df_den, 0, big = FALSE)),
    F = fmt_f(F, 2),
    p = fmt_p(p_raw),
    pbh = fmt_p(p_bh),
    n = as.character(n_subjects)
  )

write_table(tab_rq11_art %>% select(-group), "tab-rq11-art.tex",
            align = "lrrrrr",
            header = c("Term", "$df$", "$F$", "$p$", "$p_{BH}$", "Subjects"),
            groups = tab_rq11_art$group)

tab_rq11_diag <- rq11_art_diag %>%
  transmute(
    group = model,
    Term = tex_escape(term),
    `Aligned by` = tex_escape(aligned_by),
    `$F$` = formatC(F_aligned, format = "e", digits = 1),
    `Max column sum` = formatC(max_col_sum, format = "e", digits = 1),
    Alignment = if_else(alignment_ok, "valid", "invalid")
  )

write_table(tab_rq11_diag %>% select(-group), "tab-rq11-art-diagnostics.tex",
            align = "llrrl",
            header = c("Term", "Aligned by", "$F$", "Max.\\ column sum", "Alignment"),
            groups = tab_rq11_diag$group)

tab_rq11_pairwise <- rq11_pairwise %>%
  arrange(measure, phase, contrast) %>%
  transmute(
    group = paste0(measure_label, " -- ", as.character(phase)),
    Contrast = tex_escape(as.character(contrast)),
    n = as.character(n_pairs),
    Median = fmt_signed(median_diff, 3),
    p = fmt_p(p_raw),
    pbh = fmt_p(p_bh),
    r = if_else(is.na(r_rb), "--", fmt_signed(r_rb)),
    Magnitude = if_else(is.na(magnitude), "--", magnitude)
  )

write_table(tab_rq11_pairwise %>% select(-group), "tab-rq11-pairwise.tex",
            align = "lrrrrrl",
            header = c("Contrast", "$n$", "Median difference", "$p$", "$p_{BH}$",
                       "$r_{rb}$", "Magnitude"),
            groups = tab_rq11_pairwise$group)

tab_rq12_est <- rq12_estimability %>%
  select(workload, treatment, n_covered, n_subjects) %>%
  mutate(cell = sprintf("%d/%d", n_covered, n_subjects)) %>%
  select(workload, treatment, cell) %>%
  pivot_wider(names_from = treatment, values_from = cell) %>%
  mutate(workload = tex_escape(as.character(workload)))

write_table(tab_rq12_est, "tab-rq12-estimability.tex",
            align = "lrrrr",
            header = c("Workload type", tex_escape(TREAT_LABELS)))

tab_rq12_art <- rq12_art %>%
  arrange(model, match(outcome, OUTCOMES$id), term) %>%
  transmute(
    group = paste0(model, " --- ", outcome_label(outcome)),
    Term = recode(term, "treatment" = "Debloating treatment",
                  "workload" = "Workload type",
                  "treatment:workload" = "Treatment $\\times$ workload"),
    df = if_else(is.na(df_num), "--", sprintf("%d, %s", df_num, fmt_f(df_den, 0, big = FALSE))),
    F = fmt_f(F, 2),
    p = fmt_p(p_raw),
    pbh = fmt_p(p_bh),
    n = as.character(n_subjects),
    Estimable = if_else(estimable, "yes",
                        sprintf("no (%d empty, %d single-subject cells)",
                                empty_cells, thin_cells))
  )

write_table(tab_rq12_art %>% select(-group), "tab-rq12-art.tex",
            align = "lrrrrrl",
            header = c("Term", "$df$", "$F$", "$p$", "$p_{BH}$", "Subjects",
                       "Estimable"),
            groups = tab_rq12_art$group, max_rows = 40)

tab_rq12_pairwise <- rq12_pairwise %>%
  filter(!is.na(p_raw)) %>%
  arrange(match(outcome, OUTCOMES$id), workload, contrast) %>%
  transmute(
    group = outcome_label(outcome),
    `Workload type` = tex_escape(as.character(workload)),
    Contrast = tex_escape(as.character(contrast)),
    n = as.character(n_pairs),
    Median = fmt_signed(median_diff),
    p = fmt_p(p_raw),
    pbh = fmt_p(p_bh),
    r = if_else(is.na(r_rb), "--", fmt_signed(r_rb))
  )

write_table(tab_rq12_pairwise %>% select(-group), "tab-rq12-pairwise.tex",
            align = "llrrrrr",
            header = c("Workload type", "Contrast", "$n$", "Median difference",
                       "$p$", "$p_{BH}$", "$r_{rb}$"),
            groups = tab_rq12_pairwise$group, max_rows = 42)

tab_rq12_stack <- rq12_stack %>%
  arrange(match(outcome, OUTCOMES$id), treatment) %>%
  transmute(
    group = outcome_label(outcome),
    Treatment = tex_escape(as.character(treatment)),
    `$n$ single` = as.character(n_single),
    `$n$ stack` = as.character(n_stack),
    U = fmt_f(U, 1),
    p = fmt_p(p_raw),
    pbh = fmt_p(p_bh),
    d = if_else(is.na(cliff), "--", fmt_signed(cliff))
  )

write_table(tab_rq12_stack %>% select(-group), "tab-rq12-stack.tex",
            align = "lrrrrrr",
            header = c("Treatment", "$n$ single", "$n$ stack", "$U$", "$p$",
                       "$p_{BH}$", "Cliff's $\\delta$"),
            groups = tab_rq12_stack$group, max_rows = 40)

tab_rq13 <- rq13_tests %>%
  transmute(
    Outcome = outcome_label(outcome),
    n = as.character(n_pairs),
    nd = as.character(n_nonzero),
    Median = fmt_signed(median_diff),
    p = fmt_p(p_raw),
    pbh = fmt_p(p_bh),
    r = if_else(is.na(r_rb), "--", fmt_signed(r_rb)),
    Magnitude = if_else(is.na(magnitude), "--", magnitude)
  )

write_table(tab_rq13, "tab-rq13-tests.tex",
            align = "lrrrrrrl",
            header = c("Outcome", "$n$", "$n_{\neq}$", "Median difference", "$p$",
                       "$p_{BH}$", "$r_{rb}$", "Magnitude"))

tab_size <- size_tests %>%
  transmute(
    Contrast = tex_escape(as.character(contrast)),
    n = as.character(n_pairs),
    nd = as.character(n_nonzero),
    Median = fmt_signed(median_diff),
    p = fmt_p(p_raw),
    pbh = fmt_p(p_bh),
    r = if_else(is.na(r_rb), "--", fmt_signed(r_rb)),
    Magnitude = if_else(is.na(magnitude), "--", magnitude)
  )

write_table(tab_size, "tab-rq13-size.tex",
            align = "lrrrrrrl",
            header = c("Contrast", "$n$", "$n_{\\neq}$", "Median change (\\%)",
                       "$p$", "$p_{BH}$", "$r_{rb}$", "Magnitude"))

tab_size_norm <- size_normality %>%
  transmute(
    Contrast = tex_escape(contrast),
    n = as.character(n),
    W = fmt_f(W, 3),
    p = fmt_p(p),
    Normality = case_when(!testable ~ "not testable", rejects ~ "rejected",
                          TRUE ~ "not rejected")
  )

write_table(tab_size_norm, "tab-rq13-size-normality.tex",
            align = "lrrrl",
            header = c("Contrast", "$n$", "$W$", "$p$",
                       "Normality at $\\alpha=.05$"))

tab_size_variants <- size_all_variants %>%
  arrange(desc(delta)) %>%
  transmute(
    Subject = tex_escape(subject),
    Treatment = tex_escape(as.character(treat_factor(as.character(treatment)))),
    Baseline = fmt_f(base, 1),
    Variant = fmt_f(size_mb, 1),
    Change = fmt_signed(delta),
    Correct = if_else(any_correct, "yes", "no")
  )

write_table(tab_size_variants, "tab-rq13-size-variants.tex",
            align = "llrrrl",
            header = c("Subject", "Treatment", "Baseline (MB)", "Variant (MB)",
                       "Change (\\%)", "Correct"),
            max_rows = 40)

tab_blocked <- blocked_calls %>%
  arrange(desc(blocked)) %>%
  transmute(Subject = tex_escape(subject), Mode = as.character(mode),
            Blocked = as.character(blocked))

write_table(tab_blocked, "tab-rq13-blocked-calls.tex",
            align = "llr",
            header = c("Subject", "Profile generation", "Blocked system calls"))

tab_rq2 <- rq2_tests %>%
  transmute(
    Contrast = tex_escape(contrast),
    Statistic = if_else(is.na(statistic), "--",
                        sprintf("$\\chi_F^2=%s$, $df=%s$", fmt_f(statistic, 2), df)),
    n = as.character(n_pairs),
    nd = if_else(is.na(n_nonzero), "--", as.character(n_nonzero)),
    Median = if_else(is.na(median_diff), "--", fmt_signed(median_diff, 1)),
    p = fmt_p(p_raw),
    pbh = fmt_p(p_bh),
    r = if_else(is.na(r_rb), "--", fmt_signed(r_rb)),
    Magnitude = if_else(is.na(magnitude), "--", magnitude)
  )

write_table(tab_rq2, "tab-rq2.tex",
            align = "llrrrrrrl",
            header = c("Contrast", "Test statistic", "$n$", "$n_{\\neq}$",
                       "Median difference (pp)", "$p$", "$p_{BH}$", "$r_{rb}$",
                       "Magnitude"))

tab_rq2_stages <- rq2_stages %>%
  select(treatment, fail_stage, n) %>%
  pivot_wider(names_from = fail_stage, values_from = n) %>%
  mutate(Total = rowSums(across(where(is.numeric)))) %>%
  mutate(across(where(is.numeric), ~ formatC(.x, format = "d", big.mark = ","))) %>%
  mutate(treatment = tex_escape(as.character(treatment)))

write_table(tab_rq2_stages, "tab-rq2-stages.tex",
            align = "lrrrrr",
            header = c("Treatment", tex_escape(FAIL_STAGES), "Total"))

write_stat(rq1_descriptives, "rq1-descriptives")
write_stat(rq1_baseline_levels, "rq1-baseline-levels")
write_stat(rq1_normality, "rq1-normality")
write_stat(rq1_tests, "rq1-tests")
write_stat(rq1_omnibus_restricted, "rq1-omnibus-restricted")
write_stat(rq11_art, "rq11-art")
write_stat(rq11_art_diag, "rq11-art-diagnostics")
write_stat(rq11_pairwise, "rq11-pairwise")
write_stat(rq12_estimability, "rq12-estimability")
write_stat(rq12_art, "rq12-art")
write_stat(rq12_pairwise, "rq12-pairwise")
write_stat(rq12_stack, "rq12-stack")
write_stat(rq13_tests, "rq13-tests")
write_stat(size_tests, "rq13-size-tests")
write_stat(size_deltas, "rq13-size-deltas")
write_stat(size_all_variants, "rq13-size-all-variants")
write_stat(cold_trials %>% select(run_id, subject, treatment, rep, kind, duration_s,
                                  pkg0_w, pkg1_w, node_w, eb_pkg0_w,
                                  energy_node, energy_eb, intensity, size_mb),
           "cold-trials")
write_stat(cold_verify, "cold-verification")
write_stat(cold_drift_test, "cold-thermal-drift")
write_stat(cold_order_balance, "cold-order-balance")
write_stat(cold_cells, "cold-subject-treatment-cells")
write_stat(rq1_corr, "rq1-size-energy-correlation")
write_stat(size_energy, "rq1-size-energy-points")
write_stat(blocked_calls, "rq13-blocked-calls")
write_stat(correctness_cells, "rq2-correctness-cells")
write_stat(rq2_tests, "rq2-tests")
write_stat(rq2_stages, "rq2-stages")
write_stat(cells, "warm-subject-treatment-cells")
write_stat(deltas, "warm-subject-deltas")

key_numbers <- tibble::tribble(
  ~key, ~value,
  "warm_trials",              as.character(rq1_key$n_trials),
  "warm_correct",             as.character(rq1_key$n_correct),
  "warm_subjects",            as.character(rq1_key$n_subjects),
  "warm_outcomes",            as.character(sum(OUTCOMES$campaign == "warm")),
  "cold_outcomes",            as.character(sum(OUTCOMES$campaign == "cold")),
  "cold_trials",              as.character(cold_key_verify$n_trials),
  "cold_integrated",          as.character(cold_key_verify$n_energy),
  "cold_short_pulls",         as.character(cold_key_verify$n_short),
  "cold_subres_pulls",        as.character(cold_key_verify$n_subres),
  "cold_ratio_short",         sprintf("%.3f", cold_key_verify$short_ratio),
  "cold_ratio_long",          sprintf("%.3f", cold_key_verify$long_ratio),
  "cold_drift_rho",           sprintf("%.3f", cold_key_verify$drift_rho),
  "cold_drift_p",             sprintf("%.3f", cold_key_verify$drift_p),
  "cold_order_spread",        as.character(cold_key_verify$order_spread),
  "cold_channel_ratio",       sprintf("%.4f", cold_channel_agreement$median_ratio),
  "cold_channel_q05",         sprintf("%.4f", cold_channel_agreement$q05),
  "cold_channel_q95",         sprintf("%.4f", cold_channel_agreement$q95),
  "cold_contrasts",           as.character(rq1_key$n_cold_contrasts),
  "cold_contrasts_testable",  as.character(rq1_key$n_cold_test),
  "cold_contrasts_significant", as.character(rq1_key$n_cold_sig),
  "size_n_slim",              as.character(rq13_size_key$n_slim),
  "size_n_blafs",             as.character(rq13_size_key$n_blafs),
  "size_n_common",            as.character(rq13_size_key$n_common),
  "size_median_slim",         sprintf("%.2f", rq13_size_key$median_slim),
  "size_median_blafs",        sprintf("%.2f", rq13_size_key$median_blafs),
  "size_inversions",          as.character(rq13_size_key$n_inversions),
  "size_inversions_correct",  as.character(rq13_size_key$n_inv_correct),
  "corr_rho",                 sprintf("%.3f", rq1_corr$rho),
  "corr_n",                   as.character(rq1_corr$n),
  "rq1_contrasts_planned",    as.character(rq1_key$n_contrasts),
  "rq1_contrasts_testable",   as.character(rq1_key$n_contrasts_test),
  "rq1_contrasts_significant",as.character(rq1_key$n_sig_bh),
  "rq1_normality_testable",   as.character(rq1_key$n_norm_testable),
  "rq1_normality_rejected",   as.character(rq1_key$n_norm_reject),
  "subresolution_trials",     as.character(rq1_key$n_subres_trials),
  "rq1_omnibus_estimable",    as.character(rq1_key$n_omnibus_est),
  "rq11_art_subjects",        as.character(rq11_key$n_subjects_energy),
  "rq11_contrasts",           as.character(rq11_key$n_pairwise),
  "rq11_contrasts_significant", as.character(rq11_key$n_sig_bh),
  "rq13_profiles",            as.character(rq13_key$n_profiles),
  "rq13_blocked_min",         as.character(rq13_key$min_blocked),
  "rq13_blocked_max",         as.character(rq13_key$max_blocked),
  "rq13_blocked_median",      as.character(rq13_key$med_blocked),
  "rq12_art_models",          as.character(rq12_key$n_models),
  "rq12_art_estimable",       as.character(rq12_key$n_estimable),
  "rq12_pairwise_planned",    as.character(rq12_pairwise_key$planned),
  "rq12_pairwise_testable",   as.character(rq12_pairwise_key$testable),
  "rq12_pairwise_min_bh",     sprintf("%.3f", rq12_pairwise_key$min_bh),
  "rq12_stack_planned",       as.character(rq12_stack_key$planned),
  "rq12_stack_testable",      as.character(rq12_stack_key$testable),
  "rq12_stack_min_bh",        sprintf("%.3f", rq12_stack_key$min_bh),
  "rq13_static_profiles",     as.character(rq13_key$n_static),
  "rq13_dynamic_profiles",    as.character(rq13_key$n_dynamic),
  "rq2_failures",             as.character(rq2_key$n_failures),
  "rq2_output_mismatches",    as.character(rq2_key$n_mismatch),
  "rq2_nondeterministic_cells", as.character(rq2_key$n_nondet),
  "rq2_deterministic_cells",  as.character(rq2_key$n_all_or_none),
  "rq2_fail_baseline",        sprintf("%.0f", rq2_key$fail_rates[["Baseline"]]),
  "rq2_fail_slim",            sprintf("%.0f", rq2_key$fail_rates[["SlimToolkit"]]),
  "rq2_fail_blafs",           sprintf("%.0f", rq2_key$fail_rates[["BLAFS"]]),
  "rq2_fail_confine",         sprintf("%.0f", rq2_key$fail_rates[["Confine"]])
)

write_stat(key_numbers, "key_numbers")

message("done.")
