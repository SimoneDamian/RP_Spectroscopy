===== Python enviroment specifications =====

The LockingApp runs inside a specific python enviroment.
This folder contains:
	environment.yml : created using "conda env export --from-history > environment.yml" can be used to create a copy of the enviroment in a new PC via "conda env create -f environment.yml" (usually works on the same OS (Linux, in this case));
	requirements.txt : created using "pip freeze > requirements.txt", contains all the pip packages (cross-platform);
	spec_file.txt : a human-readable list of packages.

So, what one can do on the new computer:
	conda env create -f environment-portable.yml
	conda activate <env_name>
	pip install -r requirements.txt
