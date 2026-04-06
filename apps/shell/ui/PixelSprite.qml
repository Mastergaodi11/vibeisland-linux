import QtQuick 2.15

Item {
    id: sprite
    width: 22
    height: 22

    property string kind: "island"
    property color accent: "#8fb5c4"
    property color secondary: "#26303a"
    property color glow: "#ffffff"
    property bool animate: true
    property int gridSize: 8
    property int frameDuration: 220
    property int frameIndex: 0

    function framesFor(kindName) {
        var map = {
            "island": [
                [
                    "00111100",
                    "01122110",
                    "11222211",
                    "12211221",
                    "12222221",
                    "11222211",
                    "01100110",
                    "00100100"
                ],
                [
                    "00111100",
                    "01122110",
                    "11222211",
                    "12222221",
                    "12111121",
                    "11222211",
                    "01100110",
                    "00101000"
                ]
            ],
            "claude": [
                [
                    "00011000",
                    "00111100",
                    "01122110",
                    "11222211",
                    "12222221",
                    "01211210",
                    "01000010",
                    "10100101"
                ],
                [
                    "00011000",
                    "00111100",
                    "01122110",
                    "11222211",
                    "12211221",
                    "01222210",
                    "01011010",
                    "10000001"
                ]
            ],
            "codex": [
                [
                    "00011000",
                    "00122100",
                    "01222210",
                    "12211221",
                    "12222221",
                    "01222210",
                    "00122100",
                    "00011000"
                ],
                [
                    "00011000",
                    "00111100",
                    "01222210",
                    "12222221",
                    "12122121",
                    "01222210",
                    "00111100",
                    "00011000"
                ]
            ],
            "terminal": [
                [
                    "11111110",
                    "10000010",
                    "10200010",
                    "10020010",
                    "10002010",
                    "10000010",
                    "11111110",
                    "00000000"
                ],
                [
                    "11111110",
                    "10000010",
                    "12000010",
                    "10200010",
                    "10020010",
                    "10002010",
                    "11111110",
                    "00000000"
                ]
            ],
            "pin-on": [
                [
                    "00011000",
                    "00111100",
                    "00111100",
                    "00011000",
                    "00011000",
                    "00011000",
                    "00010000",
                    "00010000"
                ],
                [
                    "00011000",
                    "00122100",
                    "00122100",
                    "00011000",
                    "00011000",
                    "00010000",
                    "00010000",
                    "00010000"
                ]
            ],
            "pin-off": [
                [
                    "00011000",
                    "00111100",
                    "00111100",
                    "11011000",
                    "01101100",
                    "00010010",
                    "00010000",
                    "00010000"
                ],
                [
                    "00011000",
                    "00111100",
                    "00111100",
                    "10011001",
                    "01011010",
                    "00010100",
                    "00010000",
                    "00010000"
                ]
            ],
            "chevron-up": [
                [
                    "00000000",
                    "00011000",
                    "00111100",
                    "01100110",
                    "11000011",
                    "00000000",
                    "00000000",
                    "00000000"
                ]
            ],
            "chevron-down": [
                [
                    "00000000",
                    "00000000",
                    "00000000",
                    "11000011",
                    "01100110",
                    "00111100",
                    "00011000",
                    "00000000"
                ]
            ],
            "quiet": [
                [
                    "00011000",
                    "00111100",
                    "01111000",
                    "01110000",
                    "01110000",
                    "01111000",
                    "00111100",
                    "00011000"
                ],
                [
                    "00011000",
                    "00111100",
                    "01111100",
                    "01111000",
                    "01111000",
                    "01111100",
                    "00111100",
                    "00011000"
                ]
            ],
            "settings": [
                [
                    "00011000",
                    "00111100",
                    "01100110",
                    "11011011",
                    "11011011",
                    "01100110",
                    "00111100",
                    "00011000"
                ],
                [
                    "00011000",
                    "00111100",
                    "01111110",
                    "11011011",
                    "11011011",
                    "01111110",
                    "00111100",
                    "00011000"
                ]
            ],
            "sleep": [
                [
                    "00011000",
                    "00111100",
                    "01111110",
                    "11011011",
                    "11111111",
                    "01111110",
                    "00100100",
                    "00011000"
                ],
                [
                    "00011000",
                    "00111100",
                    "01111110",
                    "11011011",
                    "11111111",
                    "01111110",
                    "00011000",
                    "00100100"
                ]
            ],
            "alert": [
                [
                    "00011000",
                    "00011000",
                    "00011000",
                    "00011000",
                    "00011000",
                    "00000000",
                    "00011000",
                    "00011000"
                ],
                [
                    "00011000",
                    "00111100",
                    "00111100",
                    "00011000",
                    "00011000",
                    "00000000",
                    "00011000",
                    "00011000"
                ]
            ]
        }
        return map[kindName] || map["island"]
    }

    function currentFrame() {
        var frames = framesFor(kind)
        if (!frames || frames.length === 0) {
            return []
        }
        return frames[frameIndex % frames.length]
    }

    Timer {
        interval: sprite.frameDuration
        repeat: true
        running: sprite.visible && sprite.animate && sprite.framesFor(sprite.kind).length > 1
        onTriggered: {
            var frames = sprite.framesFor(sprite.kind)
            sprite.frameIndex = (sprite.frameIndex + 1) % frames.length
            canvas.requestPaint()
        }
    }

    Canvas {
        id: canvas
        anchors.fill: parent
        antialiasing: false
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            var frame = sprite.currentFrame()
            if (!frame || frame.length === 0) {
                return
            }
            var pixelWidth = Math.max(1, Math.floor(width / sprite.gridSize))
            var pixelHeight = Math.max(1, Math.floor(height / sprite.gridSize))
            var drawWidth = pixelWidth * sprite.gridSize
            var drawHeight = pixelHeight * sprite.gridSize
            var offsetX = Math.floor((width - drawWidth) / 2)
            var offsetY = Math.floor((height - drawHeight) / 2)

            for (var row = 0; row < frame.length; row += 1) {
                var line = frame[row]
                for (var col = 0; col < line.length; col += 1) {
                    var glyph = line.charAt(col)
                    if (glyph === "0") {
                        continue
                    }
                    if (glyph === "1") {
                        ctx.fillStyle = sprite.accent
                    } else if (glyph === "2") {
                        ctx.fillStyle = sprite.glow
                    } else {
                        ctx.fillStyle = sprite.secondary
                    }
                    ctx.fillRect(offsetX + col * pixelWidth, offsetY + row * pixelHeight, pixelWidth, pixelHeight)
                }
            }
        }
    }

    onKindChanged: canvas.requestPaint()
    onAccentChanged: canvas.requestPaint()
    onSecondaryChanged: canvas.requestPaint()
    onGlowChanged: canvas.requestPaint()
    onWidthChanged: canvas.requestPaint()
    onHeightChanged: canvas.requestPaint()
    Component.onCompleted: canvas.requestPaint()
}
