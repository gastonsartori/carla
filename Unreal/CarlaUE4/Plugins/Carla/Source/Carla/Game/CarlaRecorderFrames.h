// Copyright (c) 2017 Computer Vision Center (CVC) at the Universitat Autonoma
// de Barcelona (UAB).
//
// This work is licensed under the terms of the MIT license.
// For a copy, see <https://opensource.org/licenses/MIT>.

#pragma once

#include <fstream>
#include <chrono>

#pragma pack(push, 1)
struct CarlaRecorderFrame
{
  uint64_t Id;
  double DurationThis;
  double Elapsed;

  void Read(std::ifstream &InFile);

  void Write(std::ofstream &OutFile);

};
#pragma pack(pop)

class CarlaRecorderFrames
{

public:

  CarlaRecorderFrames(void);
  void Reset();

  void SetFrame(void);

  void Write(std::ofstream &OutFile);

private:

  CarlaRecorderFrame Frame;
  std::streampos OffsetPreviousFrame;
  std::chrono::time_point<std::chrono::high_resolution_clock> LastTime;
};
