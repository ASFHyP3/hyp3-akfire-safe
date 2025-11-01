# HyP3 gather-landsat

Plugin for AK fire safe applications

## Usage

The HyP3-gather-landsat plugin provides workflows (accessible directly in Python or via a CLI) that can be used to download LANDSAT images or pull fire perimeters

### `gather-landsat` workflow

The `gather_landsat` command line tool can be run using the following structure:
```bash
python -m hyp3_gather_landsat ++process gather_landsat \
  --start-date 2025-05-01 \
  --end-date 2025-05-07 \
  --location -163.97 54.756
```
Where:

* `--start-date` is the start date of the images in the format (YYYY-MM-DD)
* `--end-date` is the end date of the images in the format (YYYY-MM-DD)
* `--location` is the longitude and latitude coordinates for the location point in the format `lon lat`

> [!IMPORTANT]
> Credentials are necessary to access Landsat data. See the Credentials section for more information.

### `pull-perimeter` workflow

The `pull_perimeter` command line tool can be run using the following structure:
```bash
python -m hyp3_gather_landsat ++process pull_perimeter \
  --start-date 2025-06-01 \
  --end-date 2025-08-01 \
  --extent -169.01 52.37 -130.16 71.66
```
Where:

* `--start-date` is the start date of the images in the format (YYYY-MM-DD)
* `--end-date` is the end date of the images in the format (YYYY-MM-DD)
* `--extent` is the bounding box in longitude and latitude coordinates in the format `min_lon min_lat max_lon max_lat`

### `feds` workflow

The `feds` command line tool can be run using the following structure:
```bash
python -m hyp3_gather_landsat ++process feds \
  --path ./data \
  --start-date 2025-06-01T00:00 \
  --end-date 2025-08-01T00:00 \
  --extent -169.01 52.37 -130.16 71.66
```
Where:

* `--path` is the path for the folder that contain the text files
* `--start-date` is the start date of the images in the format (YYYY-MM-DDTHH:MM)
* `--end-date` is the end date of the images in the format (YYYY-MM-DDTHH:MM)
* `--extent` is the bounding box in longitude and latitude coordinates in the format `min_lon min_lat max_lon max_lat`

### Credentials

Generally, credentials are provided via environment variables, but some may be provided by command-line arguments or via a `.netrc` file. 

#### AWS Credentials

You must provide AWS credentials because the data is hosted by USGS in a "requester pays" bucket. To provide AWS credentials, you can either use an AWS profile specified in your `~/.aws/credentials` by exporting:
```
export AWS_PROFILE=your-profile
```
or by exporting credential environment variables:
```
export AWS_ACCESS_KEY_ID=your-id
export AWS_SECRET_ACCESS_KEY=your-key
export AWS_SESSION_TOKEN=your-token  # optional; for when using temporary credentials
```

For more information, please see: <https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html>

## Developer Setup
1. Ensure that conda is installed on your system (we recommend using [mambaforge](https://github.com/conda-forge/miniforge#mambaforge) to reduce setup times).
2. Download a local version of the `hyp3-gather-landsat` repository (`git clone https://github.com/ASFHyP3/hyp3-gather-landsat.git`)
3. In the base directory for this project call `mamba env create -f environment.yml` to create your Python environment, then activate it (`mamba activate hyp3-gather-landsat`)
4. Finally, install a development version of the package (`python -m pip install -e .`)

To run all commands in sequence use:
```bash
git clone https://github.com/ASFHyP3/hyp3-gather-landsat.git
cd hyp3-gather-landsat
mamba env create -f environment.yml
mamba activate hyp3-gather-landsat
python -m pip install -e .
```

## Contributing
Contributions to the HyP3 gather-landsat plugin are welcome! If you would like to contribute, please submit a pull request on the GitHub repository.

## Contact Us
Want to talk about HyP3 gather-landsat? We would love to hear from you!

Found a bug? Want to request a feature?
[open an issue](https://github.com/ASFHyP3/hyp3-gather-landsat/issues/new)
