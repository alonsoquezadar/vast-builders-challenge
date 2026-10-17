export function mapStyle() {
  return {
    version: 8,
    sky: {'sky-color': '#0b1520', 'horizon-color': '#2b3b4d', 'fog-color': '#10161e', 'sky-horizon-blend': 0.5, 'horizon-fog-blend': 0.7, 'fog-ground-blend': 0.25},
    sources: {
      imagery: {type: 'raster', tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'], tileSize: 256, maxzoom: 17, attribution: 'Imagery © Esri & contributors'},
      dem: {type: 'raster-dem', tiles: ['https://elevation-tiles-prod.s3.amazonaws.com/terrarium/{z}/{x}/{y}.png'], tileSize: 256, encoding: 'terrarium', maxzoom: 15, attribution: 'Elevation: AWS Terrain Tiles'},
      shade: {type: 'raster-dem', tiles: ['https://elevation-tiles-prod.s3.amazonaws.com/terrarium/{z}/{x}/{y}.png'], tileSize: 256, encoding: 'terrarium', maxzoom: 15}
    },
    layers: [
      {id: 'imagery', type: 'raster', source: 'imagery', paint: {'raster-brightness-max': 0.78, 'raster-saturation': -0.28, 'raster-contrast': 0.12}},
      {id: 'hillshade', type: 'hillshade', source: 'shade', paint: {'hillshade-shadow-color': '#000000', 'hillshade-highlight-color': '#9fb0c4', 'hillshade-accent-color': '#000000', 'hillshade-exaggeration': 0.35, 'hillshade-illumination-direction': 315}}
    ]
  };
}
