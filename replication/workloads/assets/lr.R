args <- commandArgs(trailingOnly = TRUE)
N <- as.integer(args[1])

canonical <- function(coefs) {
  ks <- sort(names(coefs))
  paste(vapply(ks, function(k) sprintf("%s=%.10f", k, coefs[[k]]), character(1)), collapse = ",")
}

digest_running <- function(prev_hex, s) {
  tmp <- tempfile()
  con <- file(tmp, "w")
  writeLines(paste0(prev_hex, s), con)
  close(con)
  on.exit(unlink(tmp), add = TRUE)
  toupper(unname(tools::md5sum(tmp)))
}

running <- ""
fit <- lm(mpg ~ wt + hp, data = mtcars)
running <- digest_running(running, canonical(coef(fit)))
cat(sprintf("COLD %s\n", running))
flush(stdout())
for (i in seq_len(N - 1)) {
  fit <- lm(mpg ~ wt + hp, data = mtcars)
  running <- digest_running(running, canonical(coef(fit)))
}
cat(sprintf("STEADY %s\n", running))
flush(stdout())
