# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [PEP 440](https://www.python.org/dev/peps/pep-0440/)
and uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.2.0]

### Added
- Added AWS Aurora RDS database for fire detection data.
- Added the ability to automatically push fire detection data to the Aurora database.

## [3.1.0]

### Added
- Added a new function to download and clip VIIRS data using `gather` workflow.
- Added a new function to download and clip Sentinel-2 data using `gather` workflow.
- Added a new function to download and clip OPERA-S1 RTC data using `gather` workflow.

### Changed
- Renamed `gather-landsat` to `gather`.
- Changed `gather-landsat` to clip an image according to the fire perimeters of a given season.

## [3.0.0]

### Added
- Added a new workflow `feds` to process fire perimeters using local files.
- Added dependencies in `pyproject.toml` and `environment.yml`.

### Changed
- Changed name of the plugin to `hyp3-akfire-safe`.

## [2.0.0]

### Added
- Added a new workflow `pull_perimeter` to pull fire perimeters from VEDA catalog.

## [1.0.0]

### Added
- Added a new function `gather_landsat` to download Landsat imagery using a location point and start and end dates.
  
## [0.1.0]

### Added
- hyp3-gather-landsat plugin created with the [HyP3 Cookiecutter](https://github.com/ASFHyP3/hyp3-cookiecutter)
