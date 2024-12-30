![image](https://github.com/user-attachments/assets/285e7866-80dc-4c64-aaa7-cbbd05bf09dd)



https://github.com/user-attachments/assets/d046cdfe-781d-4986-ac39-1afe8fe6d80a


# run_route_show
Make your own own run route show, for running_page and others

# Use
1. install [pdm](https://pdm-project.org/en/latest/)
2. put your [running_page](https://github.com/yihong0618/running_page) data to data/  `cp run_page/data.db data/`
3. pdm update
4. pdm run python -m route_show --all
5. if you want to save it to png `pdm run python -m route_show --to_png --year 2024`
6. if you want all  `pdm run python -m route_show --to_png --all`
7. if you want to generate use duckdb `pdm run python -m route_show --use_duckdb --to_png` 2024
8. when pngs is done you can generate video(copy  cp assets/github_2024.svg output) `pdm run python -m route_show --video` 
