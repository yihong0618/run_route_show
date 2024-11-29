all:
	pdm run python -m route_show 

lint:
	pdm run black .
	pdm run ruff check . --fix

format:
	pdm run black .

test:
	pdm run python -m pytest

clean:
	rm -f *.png *.svg

install:
	pdm update
