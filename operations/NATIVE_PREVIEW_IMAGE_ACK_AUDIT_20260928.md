# Managed preview image acknowledgement audit (2026-09-28)

This is a metadata-only inspection of the installed editor's managed preview
path. It did not execute an editor assembly, start the editor, send a message,
create an image, or change the accepted PAK. It narrows a possible future
native screenshot experiment; it does **not** satisfy the D11 capture gates.

The pinned `tools/bin/ModEditor/Plugins/EngineViewportPlugin.dll` has SHA-256
`c045ada12dcba0d2bb9009fb25685acd43f831ec410b492dc41d6a6ac4693c51`.
Its PE metadata and IL show this separate preview flow:

| Method | Pinned IL observation | Limited conclusion |
| --- | --- | --- |
| `PreviewProviderController..ctor` | Gets `ThumbnailsScene` and default scene conditions; subscribes `OnMessage` to `ReceiveMessage`. | This controller is configured for a thumbnail preview process, not demonstrated to be a D11 validation-scene capture. |
| `EnginePreviewProvider.GetPreviewInternal` | Calls `StartEngine`, subscribes `ImageResult`, sends `TakeScreenshot` with a target basename and `ShouldRenderHUD`, waits, checks `imageCreated`, calls `ProcessImage`, then deletes the temporary file. | A managed preview generator has a path- and success-based completion handshake. This is a different command path from the D11 runner's SSL `SaveScreenshot`. |
| `PreviewProviderController.OnMessage` | When `GameInformation` is non-null, compares its `ProcessId` with `OwnEngineProcessId`. A null `GameInformation` takes the dispatch branch without that comparison. It dispatches name `ImageResult`, reads a string and Boolean, then invokes `ImageResult`. The event type is `Action<string,bool>`. | The managed bridge has a conditional process-ID check and a path/success event; it does not independently authenticate the sender or deliver PNG bytes or a digest. |
| `<GetPreviewInternal>g__OnImageReady|0` | Checks the returned path against its expected `.png` path, stores the Boolean as `imageCreated`, then signals the wait event. | A mismatched target cannot complete this preview request; the Boolean is checked before image use. |
| `EnginePreviewProvider.ProcessImage` | Calls `File.ReadAllBytes` on the resulting path and decodes it as an image. | The editor reads local image bytes after the success message. The engine does not report the byte count or SHA-256 of those bytes. |

The installed native `Roadcraft ModEditor.exe`, SHA-256
`ce6a48b1c73bea0876376d3251a6810b4a9913a7d500226e42bb2c605f3810b7`,
contains an ASCII `TakeScreenshot` token at file offset 85,705,120. This
supports the command-name association only; the managed IL is the evidence
for the callback's shape. No live call or scene identity was tested.

For reproducibility, this PowerShell 7 block reads PE metadata only. It
refuses a changed DLL and resolves operands at exact instruction offsets
observed in that pinned DLL:

~~~powershell
$path = 'C:\Program Files (x86)\Steam\steamapps\common\RoadCraft\tools\bin\ModEditor\Plugins\EngineViewportPlugin.dll'
$pin = 'c045ada12dcba0d2bb9009fb25685acd43f831ec410b492dc41d6a6ac4693c51'
if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $pin) {
  throw 'EngineViewportPlugin.dll changed'
}
$checks = @(
  @('PreviewProviderController','.ctor',0x56,'get_ThumbnailsScene'),
  @('PreviewProviderController','.ctor',0x94,'add_ReceiveMessage'),
  @('PreviewProviderController','OnMessage',0x19,'get_OwnEngineProcessId'),
  @('PreviewProviderController','OnMessage',0x25,'get_ProcessId'),
  @('PreviewProviderController','OnMessage',0x76,'ImageResult'),
  @('PreviewProviderController','OnMessage',0xd3,'ReadString'),
  @('PreviewProviderController','OnMessage',0xdb,'ReadBool'),
  @('EnginePreviewProvider','GetPreviewInternal',0x37,'StartEngine'),
  @('EnginePreviewProvider','GetPreviewInternal',0x1a7,'add_ImageResult'),
  @('EnginePreviewProvider','GetPreviewInternal',0x1cb,'TakeScreenshot'),
  @('EnginePreviewProvider','GetPreviewInternal',0x1e8,'SendMessage'),
  @('EnginePreviewProvider','GetPreviewInternal',0x2bc,'imageCreated'),
  @('EnginePreviewProvider','GetPreviewInternal',0x336,'ProcessImage'),
  @('EnginePreviewProvider','GetPreviewInternal',0x343,'Delete'),
  @('<>c__DisplayClass15_0','<GetPreviewInternal>g__OnImageReady|0',0x08,'op_Equality'),
  @('<>c__DisplayClass15_0','<GetPreviewInternal>g__OnImageReady|0',0x14,'imageCreated'),
  @('<>c__DisplayClass15_0','<GetPreviewInternal>g__OnImageReady|0',0x24,'Set'),
  @('EnginePreviewProvider','ProcessImage',0x08,'ReadAllBytes')
)
$stream = [IO.File]::OpenRead($path)
try {
  $pe = [System.Reflection.PortableExecutable.PEReader]::new($stream)
  $md = [System.Reflection.Metadata.PEReaderExtensions]::GetMetadataReader($pe)
  foreach ($spec in $checks) {
    $found = $false
    foreach ($typeHandle in $md.TypeDefinitions) {
      $type = $md.GetTypeDefinition($typeHandle)
      if ($md.GetString($type.Name) -cne $spec[0]) { continue }
      foreach ($methodHandle in $type.GetMethods()) {
        $method = $md.GetMethodDefinition($methodHandle)
        if ($md.GetString($method.Name) -cne $spec[1]) { continue }
        if ($method.RelativeVirtualAddress -eq 0) { continue }
        $il = [System.Reflection.Metadata.PEReaderExtensions]::GetMethodBody(
          $pe, $method.RelativeVirtualAddress).GetILBytes()
        if ($spec[0] -ceq 'PreviewProviderController' -and
            $spec[1] -ceq 'OnMessage' -and
            (@($il[0x02],$il[0x03],$il[0x42],$il[0x45],$il[0x46],$il[0x4c]) -join ',') -cne
            '44,62,22,44,5,4') {
          throw 'OnMessage null-GameInformation branch changed'
        }
        $offset = [int]$spec[2]
        $opcode = [int]$il[$offset]
        if ($opcode -notin @(0x28,0x6f,0x72,0x7b,0x7d)) {
          throw "Unexpected opcode at $($spec[0]).$($spec[1]) 0x$($offset.ToString('x'))"
        }
        $token = [BitConverter]::ToInt32($il, $offset + 1)
        if ($opcode -eq 0x72) {
          $handle = [System.Reflection.Metadata.Ecma335.MetadataTokens]::UserStringHandle(
            $token -band 0x00ffffff)
          $name = $md.GetUserString($handle)
        } else {
          $handle = [System.Reflection.Metadata.Ecma335.MetadataTokens]::EntityHandle($token)
          $name = switch ($handle.Kind) {
            'MethodDefinition' { $md.GetString($md.GetMethodDefinition($handle).Name) }
            'MemberReference' { $md.GetString($md.GetMemberReference($handle).Name) }
            'FieldDefinition' { $md.GetString($md.GetFieldDefinition($handle).Name) }
            default { throw "Unexpected token kind at $offset" }
          }
        }
        if ($name -cne $spec[3]) { throw "Unexpected operand: $name" }
        '{0}.{1} 0x{2:x4}: {3}' -f $spec[0],$spec[1],$offset,$name
        $found = $true
        break
      }
      if ($found) { break }
    }
    if (-not $found) { throw "Missing method: $($spec[0]).$($spec[1])" }
  }
} finally { $stream.Dispose() }
~~~

The `ImageResult` route is a useful lead, but the shipped D11 runner uses
`SaveScreenshot` through Automation/ExecSsl and has no demonstrated
`ImageResult` subscription. The preview controller's own process and
`ThumbnailsScene` are not authenticated as the D11 validation-scene session.
Even within preview, a path plus Boolean does not bind the engine to the exact
PNG bytes later read from disk. It provides no engine-loaded scene-buffer
digest, complete lighting readback, or proof for the 45 D11 views. Keep
`loadedSceneVerified` and `captureProcessAuthenticated` false.

The smallest later runtime experiment would use a disposable editor session
to learn whether this callback can be bound to the *same owned D11 process,
validation scene, request nonce, and target* as one scratch screenshot. The
acceptance rule would still require an engine-side digest (or engine-supplied
bytes) for the completed PNG and loaded scene resource. The metadata check
above is safe to rerun offline now; the runtime experiment is not authorized
by this audit.
