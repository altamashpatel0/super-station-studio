const { contextBridge } = require('electron');
contextBridge.exposeInMainWorld('superStation', {
  desktop: true,
  version: '1.0.0',
});
