# GOES archive check for the Garnet video

Decision: use the saved wind-and-terrain scenario for this release. GOES has not been incorporated into the simulation.

The research worker found the public product but did not verify the date-specific archive. The parent then queried two NOAA S3 prefixes directly on 17 October 2026. Each returned HTTP 200 and six NetCDF objects, with starts ten minutes apart.

- [27 August 2025, 23 UTC](https://noaa-goes18.s3.amazonaws.com/?list-type=2&prefix=ABI-L2-FDCF/2025/239/23/&max-keys=8).
- [28 August 2025, 05 UTC](https://noaa-goes18.s3.amazonaws.com/?list-type=2&prefix=ABI-L2-FDCF/2025/240/05/&max-keys=8).

First confirmed object: `ABI-L2-FDCF/2025/239/23/OR_ABI-L2-FDCF-M6_G18_s20252392300216_e20252392309524_c20252392310039.nc`.

This proves that files exist at both ends of the requested interval. It does not establish completeness between them or a valid fire detection over Garnet. No NetCDF file was downloaded or interpreted.

[NASA describes GOES ABI fire observations](https://wiki.earthdata.nasa.gov/spaces/FIRMS/blog/2024/06/25/377718041/Geostationary%2BActive%2BFire%2BDetection%2BData%2Bin%2BFIRMS) at ten-minute intervals and approximately 2 km native resolution, with larger pixels away from nadir. These observations could add evidence about activity between polar-orbiting overpasses. They would not by themselves validate a precise fire edge in the video.

The next data task is to retrieve a small set of those files, verify their quality flags, project the Garnet location onto the ABI grid, and inspect the local fire-mask and radiative-power values. That extraction is outside this release. No unsupported fire-mask codes, minimum detectable area, or five-minute FDCF cadence are assumed.
