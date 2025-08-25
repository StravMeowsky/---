import mido
from typing import List, Dict, Any, Tuple, Optional


class BeatMidiConverter:
    """优化的Beat到MIDI转换器，支持beat合并"""

    def __init__(self, ticks_per_beat: int = 480):
        self.ticks_per_beat = ticks_per_beat

    def merge_beats(
        self,
        beat1: List[float],
        beat2: List[float],
        beat_positions1: List[int],
        downbeats1: List[float],
        downbeats2: List[float],
        tolerance: float = 0.3,
    ) -> Dict[str, List[float]]:
        """合并两个beat序列，重叠部分优先使用beat1，并返回beats、beat_positions和downbeats。

        Args:
            beat1: 第一个beat序列（不从0开始，优先级高, allin1）
            beat2: 第二个beat序列（从0开始，填补空白, gorta）
            beat_positions1: 第一个beat序列的beat位置
            downbeats1: 第一个beat序列的downbeats
            downbeats2: 第二个beat序列的downbeats
            tolerance: 时间误差容忍度（秒）

        Returns:
            一个字典，包括合并后的 `beats`、`beat_positions` 和 `downbeats`
        """
        # 边界情况：如果其中一个序列为空，返回另一个序列
        if not beat1:
            return {
                "beats": beat2,
                "beat_positions": [
                    1 if b in downbeats2 else 2 for b in beat2
                ],  # 生成 position: 1 表示 downbeat
                "downbeats": downbeats2,
            }
        if not beat2:
            return {
                "beats": beat1,
                "beat_positions": [
                    1 if b in downbeats1 else 2 for b in beat1
                ],  # 生成 position: 1 表示 downbeat
                "downbeats": downbeats1,
            }

        # 获取beat1的时间范围
        beat1_start = min(beat1)
        beat1_end = max(beat1)

        # 分离 beat2 中的不重叠部分
        beat2_before = [
            (b, p)
            for b, p in zip(beat2, range(1, len(beat2) + 1))
            if b < beat1_start - tolerance
        ]
        beat2_after = [
            (b, p)
            for b, p in zip(beat2, range(1, len(beat2) + 1))
            if b > beat1_end + tolerance
        ]

        print(f"Beat2前部分: {len(beat2_before)} 个 beat")
        print(f"Beat1主体: {len(beat1)} 个 beat")
        print(f"Beat2后部分: {len(beat2_after)} 个 beat")

        # 合并所有部分
        merged_beats = beat2_before + list(zip(beat1, beat_positions1)) + beat2_after

        # 按时间排序
        merged_beats.sort(key=lambda x: x[0])

        # 移除过于接近的beat（在容忍度范围内）
        filtered_beats = [merged_beats[0]]
        for beat, position in merged_beats[1:]:
            if abs(beat - filtered_beats[-1][0]) > tolerance:
                filtered_beats.append((beat, position))

        # 提取合并后的 beat
        final_beats = [b for b, _ in filtered_beats]

        # 生成final_positions，1表示downbeat，其他按小节顺序生成
        final_positions = []
        for beat in final_beats:
            if beat in downbeats1 or beat in downbeats2:
                final_positions.append(1)  # 如果是 downbeat, 位置为 1
            else:
                # 对于其他beat，设置为 0
                final_positions.append(0)

        num_beats_per_quarter = max(beat_positions1)
        num_start_beats_before_downbeat = final_positions[
            : final_positions.index(1)
        ].count(0)
        start_number = num_beats_per_quarter - num_start_beats_before_downbeat + 1

        for i in range(len(final_positions)):
            beat_num = (start_number + i) % num_beats_per_quarter
            final_positions[i] = beat_num if beat_num != 0 else num_beats_per_quarter

        # downbeats是final position = 1时的beats
        merged_downbeats = [b for b, p in zip(final_beats, final_positions) if p == 1]

        print(f"原始Beat1数量: {len(beat1)}, Beat2数量: {len(beat2)}")
        print(f"合并后Beat数量: {len(final_beats)}")
        print(f"合并后Downbeat数量: {len(merged_downbeats)}")

        return final_beats, final_positions, merged_downbeats

    def time_to_beat_position(self, time_seconds: float, beats: List[float]) -> float:
        """将时间（秒）转换为beat位置"""
        if not beats:
            return 0.0

        for i, beat_time in enumerate(beats):
            if beat_time >= time_seconds:
                if i == 0:
                    return 0.0
                else:
                    prev_beat_time = beats[i - 1]
                    beat_interval = beat_time - prev_beat_time
                    if beat_interval > 0:
                        time_offset = time_seconds - prev_beat_time
                        return i + (time_offset / beat_interval)
                    else:
                        return float(i)

        # 处理超出范围的时间
        if len(beats) >= 2:
            last_interval = beats[-1] - beats[-2]
            if last_interval > 0:
                extra_time = time_seconds - beats[-1]
                return len(beats) + (extra_time / last_interval)

        return len(beats)

    def calculate_tempo_from_beats(
        self, beats: List[float]
    ) -> List[Tuple[float, float]]:
        """根据beat信息计算速度"""
        if len(beats) < 2:
            return [(0.0, 120.0)]

        tempo_changes = []
        for i in range(len(beats) - 1):
            interval = beats[i + 1] - beats[i]
            if interval > 0:
                bpm = 60.0 / interval
                # 限制BPM范围，避免极端值
                tempo_changes.append((float(i), bpm))

        return tempo_changes

    def create_segment_markers(
        self, beats: List[float], segments: List[Dict[str, Any]]
    ) -> List[Tuple[float, str]]:
        """根据分段信息创建marker"""
        if not beats or not segments:
            return []

        markers = []
        for segment in segments:
            start_time = segment.get("start", 0.0)
            label = segment.get("label", "unknown")
            beat_position = self.time_to_beat_position(start_time, beats)
            markers.append((beat_position, label))

        markers.sort(key=lambda x: x[0])
        return markers

    def beats_to_ticks(self, beats: float) -> int:
        """将beat转换为MIDI ticks"""
        return int(beats * self.ticks_per_beat)

    def bpm_to_tempo(self, bpm: float) -> int:
        """将BPM转换为MIDI tempo值"""
        return int(60000000 / bpm)

    def create_tempo_track(self, beats: List[float]) -> mido.MidiTrack:
        """保留真实开始时间，让第一个 beat 落在 beats[0] 秒，而不是强行从0开始"""
        track = mido.MidiTrack()
        track.append(mido.MetaMessage("track_name", name="Tempo Track", time=0))

        # MIDI tick=0 对应 beats[0] 秒
        real_start_time = beats[0]

        # 前导静音段
        if real_start_time > 0:
            pre_bpm = 60.0 / real_start_time
            pre_tempo = int(60_000_000 / pre_bpm)
            track.append(mido.MetaMessage("set_tempo", tempo=pre_tempo, time=0))
            current_tick = self.ticks_per_beat
        else:
            current_tick = 0

        for i in range(1, len(beats)):
            # 每个 tempo 起始 tick
            tick = current_tick + (i - 1) * self.ticks_per_beat
            delta_ticks = tick - sum(m.time for m in track if hasattr(m, "time"))

            interval = beats[i] - beats[i - 1]
            if interval <= 0:
                continue

            bpm = 60.0 / interval
            tempo = int(60_000_000 / bpm)

            track.append(mido.MetaMessage("set_tempo", tempo=tempo, time=delta_ticks))

        track.append(mido.MetaMessage("end_of_track", time=0))
        return track

    def create_marker_track(self, markers: List[Tuple[float, str]]) -> mido.MidiTrack:
        """创建标记轨道"""
        track = mido.MidiTrack()
        track.append(mido.MetaMessage("track_name", name="Markers", time=0))

        current_time = 0
        for beat_pos, label in markers:
            target_time = self.beats_to_ticks(beat_pos)
            delta_time = max(0, target_time - current_time)
            marker_msg = mido.MetaMessage("marker", text=label, time=delta_time)
            track.append(marker_msg)
            current_time = target_time

        track.append(mido.MetaMessage("end_of_track", time=0))
        return track

    def generate_midi(
        self,
        output_file: str,
        beat_data1: Dict[str, Any],
        beat_data2: Optional[Dict[str, Any]] = None,
        tolerance: float = 0.1,
    ):
        """生成MIDI文件"""
        beats1 = beat_data1.get("beats", [])
        beat_positions1 = beat_data1.get("beat_positions", [])
        downbeats1 = beat_data1.get("downbeats", [])

        if beat_data2:
            beats2 = beat_data2.get("beats", [])
            downbeats2 = beat_data2.get("downbeats", [])
            print(f"Beat1数量: {len(beats1)}, Beat2数量: {len(beats2)}")

            # 合并beats
            merged_beats, beat_positions, downbeats = self.merge_beats(
                beats1, beats2, beat_positions1, downbeats1, downbeats2, tolerance
            )
            prefix_beat = beat_positions.index(1)
            final_beats = merged_beats
        else:
            final_beats = beats1
            print(f"Beat数量: {len(final_beats)}")

        # 创建分段标记
        markers = []
        segments = beat_data1.get("segments", [])
        markers = self.create_segment_markers(final_beats, segments)
        print(f"分段标记: {len(markers)} 个")

        # 创建MIDI文件
        mid = mido.MidiFile(ticks_per_beat=self.ticks_per_beat)

        # 添加时间签名
        time_sig_track = mido.MidiTrack()
        time_sig_track.append(
            mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0)
        )
        mid.tracks.append(time_sig_track)

        # 添加速度轨道
        tempo_track = self.create_tempo_track(final_beats)
        mid.tracks.append(tempo_track)

        # 添加标记轨道（如果有）
        if markers:
            marker_track = self.create_marker_track(markers)
            mid.tracks.append(marker_track)

        # 保存文件
        mid.save(output_file)

        return prefix_beat
