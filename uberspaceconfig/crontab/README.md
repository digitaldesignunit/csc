# Uberspace Crontab

- These are the individual cronjobs fro CSC.
- For uberspace, they are all in one crontab
- To edit the crontab, run `crontab -e` in the ssh shell
- Paste the cronjobs you need/want into the tab
- Adjust timings if you deem it necessary
- Each entry has `MAILTO="<maintainer email>"` as a placeholder: put the real address
  only in the server's crontab (`crontab -e`), never in this repository
