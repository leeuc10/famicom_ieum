/*
 * FAMI FIGHTERS - 컨트롤러 펌웨어 (ESP32-S3, USB HID 키보드)
 *
 * 두 대에 완전히 같은 펌웨어를 굽는다. 1P/2P 는 GPIO8 점퍼로 정한다.
 *   - GPIO8 개방(내부 풀업) -> 1P
 *   - GPIO8 을 GND 에 연결  -> 2P
 *
 * 배선: 각 스위치의 한쪽 다리를 아래 GPIO 에, 반대쪽 다리를 GND 에 문다.
 *       내부 풀업을 켜므로 외부 저항은 필요 없다. 눌리면 LOW.
 *
 *   UP=4  DOWN=5  LEFT=6  RIGHT=7  A=15  B=16  START=17  SELECT=18
 *
 * GPIO19/20 은 네이티브 USB(D-/D+)라 절대 쓰지 않는다. HID 가 그 위에서 돈다.
 *
 * 아두이노 IDE 설정 (안 하면 HID 장치로 안 뜬다):
 *   Board       : ESP32S3 Dev Module
 *   USB Mode    : USB-OTG (TinyUSB)      <-- 반드시 변경
 *   USB CDC On Boot : Disabled
 *   업로드는 UART 포트, 파이에 연결할 때는 USB(네이티브) 포트를 쓴다.
 */

#include "USB.h"
#include "USBHIDKeyboard.h"

USBHIDKeyboard Keyboard;

// GPIO8 을 GND 로 내리면 2P 가 된다.
constexpr uint8_t PIN_PLAYER_SELECT = 8;

// 스위치가 접점에서 떠는 시간. 5ms 는 60fps 기준 0.3프레임이라
// 조작감에 영향을 주지 않으면서 채터링을 걸러낸다.
constexpr uint32_t DEBOUNCE_MS = 5;

struct Button {
  uint8_t pin;
  uint8_t key_1p;
  uint8_t key_2p;
};

// input_adapter.py 의 KEYBOARD_LAYOUTS 와 반드시 같은 매핑이어야 한다.
const Button BUTTONS[] = {
  { 4,  'w',        KEY_UP_ARROW    },  // UP     - 점프
  { 5,  's',        KEY_DOWN_ARROW  },  // DOWN   - 가드/앉기 예약
  { 6,  'a',        KEY_LEFT_ARROW  },  // LEFT
  { 7,  'd',        KEY_RIGHT_ARROW },  // RIGHT
  { 15, 'f',        ','             },  // A      - 펀치
  { 16, 'g',        '.'             },  // B      - 킥
  { 17, KEY_RETURN, KEY_RETURN      },  // START  - 시작/일시정지
  { 18, KEY_ESC,    KEY_ESC         },  // SELECT - 타이틀 복귀
};

constexpr size_t BUTTON_COUNT = sizeof(BUTTONS) / sizeof(BUTTONS[0]);

bool is_2p = false;
bool stable_state[BUTTON_COUNT];   // 디바운스가 끝난 상태 (true = 눌림)
bool last_raw[BUTTON_COUNT];       // 직전에 읽은 원시 상태
uint32_t last_change_ms[BUTTON_COUNT];

inline uint8_t keyFor(size_t i) {
  return is_2p ? BUTTONS[i].key_2p : BUTTONS[i].key_1p;
}

void setup() {
  for (size_t i = 0; i < BUTTON_COUNT; i++) {
    pinMode(BUTTONS[i].pin, INPUT_PULLUP);
    stable_state[i] = false;
    last_raw[i] = false;
    last_change_ms[i] = 0;
  }

  pinMode(PIN_PLAYER_SELECT, INPUT_PULLUP);
  delay(20);                                        // 풀업이 안정될 때까지 기다린다
  is_2p = (digitalRead(PIN_PLAYER_SELECT) == LOW);

  // 부스에서 어느 쪽이 어느 패드인지 lsusb 로 바로 알아볼 수 있게 이름을 나눈다.
  USB.productName(is_2p ? "FAMI FIGHTERS PAD 2P" : "FAMI FIGHTERS PAD 1P");
  USB.manufacturerName("FAMI FIGHTERS");
  Keyboard.begin();
  USB.begin();
}

void loop() {
  const uint32_t now = millis();

  for (size_t i = 0; i < BUTTON_COUNT; i++) {
    const bool raw = (digitalRead(BUTTONS[i].pin) == LOW);   // 풀업이라 눌리면 LOW

    if (raw != last_raw[i]) {
      // 값이 막 흔들린 참이다. 타이머를 다시 켜고 안정될 때까지 보류한다.
      last_raw[i] = raw;
      last_change_ms[i] = now;
      continue;
    }
    if (raw == stable_state[i] || now - last_change_ms[i] < DEBOUNCE_MS) {
      continue;
    }

    stable_state[i] = raw;
    if (raw) {
      Keyboard.press(keyFor(i));
    } else {
      Keyboard.release(keyFor(i));
    }
  }

  // delay 를 두지 않는다. 폴링 주기가 곧 입력 지연이다.
}
