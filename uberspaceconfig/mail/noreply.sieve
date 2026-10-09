# Sieve filter for the CSC noreply mailbox (decision 8.124, amended 2026-10-08).
#
# The backend sends every mail from the noreply address; replies normally go to
# the Reply-To (support or the acting moderator). What still arrives here:
# bounces (mistyped invitation addresses, full mailboxes), clients that ignore
# Reply-To, and spam. This script
#   1. drops spam (nobody reads this mailbox),
#   2. forwards everything else to support,
#   3. answers human senders once a week with a short note,
#   4. stores nothing: `redirect` cancels the implicit keep.
#
# Install on Uberspace (check the noreply / support addresses and the URL below):
#   uberspace mail spamfolder enable      # Sieve needs it (Uberspace manual)
#   mkdir -p ~/users/noreply/sieve
#   cp noreply.sieve ~/users/noreply/sieve/noreply.sieve
#   sievec ~/users/noreply/sieve/noreply.sieve          # compile check
#   cd ~/users/noreply && ln -sf sieve/noreply.sieve .dovecot.sieve
# Errors: ~/users/noreply/.dovecot.sieve.log (written only on a Sieve error).

require ["vacation", "variables", "relational", "comparator-i;ascii-numeric"];

# 1. Spam (Rspamd score 5 or more): drop it, do not forward, do not answer.
if allof (
  not header :matches "X-Rspamd-Score" "-*",
  header :value "ge" :comparator "i;ascii-numeric" "X-Rspamd-Score" "5")
{
  discard;
  stop;
}

# 2. Everything else goes to support. The original From stays, so support can
#    answer the sender directly; bounces show which invitation failed.
redirect "support@2ndchances.build";

# 3. A short answer to human senders, at most once a week per sender. Sieve's
#    vacation never answers bounces (empty envelope sender), auto-replies
#    (Auto-Submitted), mailing lists or bulk mail, so no mail loops.
if header :matches "Subject" "*" {
  set "subject" "${1}";
}
vacation
  :days 7
  :addresses ["noreply@2ndchances.build"]
  :from "noreply@2ndchances.build"
  :subject "Re: ${subject}"
"Hello,

this address only sends automatic messages from the Catalog of Second Chances
and is not read. Your message has been forwarded to our support team
(support@2ndchances.build), who will get back to you if needed.

For questions about a dataset, please contact its moderator.

Catalog of Second Chances
https://2ndchances.build";

# No `keep`: the redirect above already cancelled the implicit keep, so the
# message is not stored in this mailbox.
