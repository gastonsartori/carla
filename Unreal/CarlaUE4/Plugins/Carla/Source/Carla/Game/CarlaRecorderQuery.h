// Copyright (c) 2017 Computer Vision Center (CVC) at the Universitat Autonoma
// de Barcelona (UAB).
//
// This work is licensed under the terms of the MIT license.
// For a copy, see <https://opensource.org/licenses/MIT>.

#pragma once

#include <fstream>
#include "Carla/Game/CarlaRecorderInfo.h"
#include "Carla/Game/CarlaRecorderFrames.h"
#include "Carla/Game/CarlaRecorderEventAdd.h"
#include "Carla/Game/CarlaRecorderEventDel.h"
#include "Carla/Game/CarlaRecorderEventParent.h"
#include "Carla/Game/CarlaRecorderCollision.h"
#include "Carla/Game/CarlaRecorderPosition.h"
#include "Carla/Game/CarlaRecorderState.h"

class CarlaRecorderQuery
{

  #pragma pack(push, 1)
  struct Header
  {
    char Id;
    uint32_t Size;
  };
  #pragma pack(pop)

public:

  // forwarded to replayer
  std::string QueryInfo(std::string Filename, bool bShowAll = false);
  std::string QueryCollisions(std::string Filename, char Category1 = 'a', char Category2 = 'a');
  std::string QueryBlocked(std::string Filename, double MinTime = 30, double MinDistance = 10);

private:

  std::ifstream File;
  Header Header;
  CarlaRecorderInfo RecInfo;
  CarlaRecorderFrame Frame;
  CarlaRecorderEventAdd EventAdd;
  CarlaRecorderEventDel EventDel;
  CarlaRecorderEventParent EventParent;
  CarlaRecorderPosition Position;
  CarlaRecorderCollision Collision;
  CarlaRecorderStateTrafficLight StateTraffic;

  bool ReadHeader(void);
  void SkipPacket(void);

  // read the start info structure and check the magic string
  bool CheckFileInfo(std::stringstream &Info);
};
