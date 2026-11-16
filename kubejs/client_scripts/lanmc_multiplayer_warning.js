// The same Minecraft option that the third-party server screen's checkbox sets.
ClientEvents.generateAssets('after_mods', () => {
  const Minecraft = Java.loadClass('net.minecraft.client.Minecraft')
  Minecraft.getInstance().options.skipMultiplayerWarning = true
})
