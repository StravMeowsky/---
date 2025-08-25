# -*- coding: utf-8 -*-
"""
Beat到MIDI转换器
1. 支持合并两个beat文件（第一个不从0开始，第二个从0开始）
2. 根据beat信息计算速度
3. 根据分段信息提供marker
"""
import mido
import random
import json
import argparse
from typing import List, Dict, Any
import os
import mido
from mido import MidiFile, MidiTrack
import pretty_midi

from beat_midi_converter import BeatMidiConverter


class DrumLoopSampler:
    def __init__(self, ticks_per_beat: int = 480, beats_per_bar: int = 4):
        self.ticks_per_beat = ticks_per_beat
        self.beats_per_bar = beats_per_bar

    def extract_drum_events(self, midi_file: str) -> List[Dict[str, Any]]:
        """从drum loop MIDI文件中提取鼓点数据"""
        drum_events = []
        midi = MidiFile(midi_file)

        for track in midi.tracks:
            for msg in track:
                if msg.type == "note_on" or msg.type == "note_off":
                    drum_events.append(
                        {
                            "time": msg.time,
                            "note": msg.note,
                            "velocity": msg.velocity,
                            "type": msg.type,
                        }
                    )
        return drum_events

    def sample_drum_loops(
        self,
        target_midi_file: str,
        loop_folder_path: str,
        output_file: str,
        prefix_beat: int,
    ) -> None:
        """根据目标MIDI文件和单个loop文件夹路径采样并填充鼓点"""
        # 读取目标MIDI文件
        target_midi = MidiFile(target_midi_file)

        # 从每个drum loop文件夹中提取鼓点
        all_drum_events = {
            "start": [],
            "mid": {
                "regular": [],
                "transition": {
                    "small": [],
                    "big": [],
                },
            },
            "end": [],
        }

        # 遍历loop文件夹的子文件夹
        for folder_name in os.listdir(loop_folder_path):
            folder_path = os.path.join(loop_folder_path, folder_name)
            if not os.path.isdir(folder_path):
                continue

            if folder_name == "start":
                # 处理 start 文件夹
                for file_name in os.listdir(folder_path):
                    if file_name.endswith(".mid"):
                        midi_file_path = os.path.join(folder_path, file_name)
                        drum_events = self.extract_drum_events(midi_file_path)
                        all_drum_events["start"].append(drum_events)

            elif folder_name == "mid":
                # 处理 mid 文件夹中的子文件夹
                for subfolder_name in os.listdir(folder_path):
                    subfolder_path = os.path.join(folder_path, subfolder_name)
                    if not os.path.isdir(subfolder_path):
                        continue

                    if subfolder_name == "regular":
                        # 处理 regular 文件夹
                        for file_name in os.listdir(subfolder_path):
                            if file_name.endswith(".mid"):
                                midi_file_path = os.path.join(subfolder_path, file_name)
                                drum_events = self.extract_drum_events(midi_file_path)
                                all_drum_events["mid"]["regular"].append(drum_events)

                    elif subfolder_name == "transition":
                        # 处理 transition 文件夹中的 small 和 big
                        for transition_type in ["small", "big"]:
                            transition_folder_path = os.path.join(
                                subfolder_path, transition_type
                            )
                            if os.path.isdir(transition_folder_path):
                                for file_name in os.listdir(transition_folder_path):
                                    if file_name.endswith(".mid"):
                                        midi_file_path = os.path.join(
                                            transition_folder_path, file_name
                                        )
                                        drum_events = self.extract_drum_events(
                                            midi_file_path
                                        )
                                        all_drum_events["mid"]["transition"][
                                            transition_type
                                        ].append(drum_events)

            elif folder_name == "end":
                # 处理 end 文件夹
                for file_name in os.listdir(folder_path):
                    if file_name.endswith(".mid"):
                        midi_file_path = os.path.join(folder_path, file_name)
                        drum_events = self.extract_drum_events(midi_file_path)
                        all_drum_events["end"].append(drum_events)

        # 创建轨道
        track = MidiTrack()
        target_midi.tracks.append(track)

        # 获取目标MIDI的时间轴（在节奏基础上）
        target_beats = self.get_target_beats(target_midi)

        # 采样和插入鼓点
        current_beat_idx = 0
        total_beats = len(target_beats)

        # 定义循环长度（以小节为单位）
        start_loop_length = self.beats_per_bar * 4 + prefix_beat + 1  # start: 4小节
        mid_loop_length = self.beats_per_bar * 2  # mid: 2小节
        end_loop_length = self.beats_per_bar * 5  # end: 4小节

        # 定义中间部分的采样顺序
        mid_sampling_order = [
            "regular",
            "transition-small",
            "regular",
            "transition-big",
        ]

        mid_order_index = 0
        # 1. 开头部分：从start采样4小节
        if current_beat_idx < start_loop_length:
            drum_event = random.choice(all_drum_events["start"])
            for event in drum_event:
                if len(track) == 0:
                    event["time"] += 480 * (prefix_beat + 1)
                track.append(
                    mido.Message(
                        event["type"],
                        note=event["note"],
                        velocity=event["velocity"],
                        time=event["time"],
                    )
                )
            current_beat_idx += start_loop_length

        # 2. 中间部分：按照顺序采样
        while current_beat_idx < total_beats - end_loop_length:
            # 获取当前采样类型
            current_mid_type = mid_sampling_order[
                mid_order_index % len(mid_sampling_order)
            ]

            # 根据类型获取鼓点
            if current_mid_type == "regular":
                drum_events = random.choice(all_drum_events["mid"]["regular"])
            elif current_mid_type == "transition-small":
                drum_events = random.choice(
                    all_drum_events["mid"]["transition"]["small"]
                )
            else:  # transition-big
                drum_events = random.choice(all_drum_events["mid"]["transition"]["big"])

            # 插入鼓点
            for event in drum_events:
                track.append(
                    mido.Message(
                        event["type"],
                        note=event["note"],
                        velocity=event["velocity"],
                        time=event["time"],
                    )
                )

            current_beat_idx += mid_loop_length
            mid_order_index += 1

        # 3. 结尾部分：从end采样4小节
        if current_beat_idx < total_beats:
            drum_event = random.choice(all_drum_events["end"])
            for event in drum_event:
                track.append(
                    mido.Message(
                        event["type"],
                        note=event["note"],
                        velocity=event["velocity"],
                        time=event["time"],
                    )
                )
            current_beat_idx += end_loop_length

        # 保存最终MIDI文件
        target_midi.save(output_file)
        print(f"MIDI文件已保存到: {output_file}")

    def get_target_beats(self, midi: str) -> List[float]:
        """从目标MIDI文件中提取出beat信息"""
        # 这个得跟分段信息结合，确认一下起始点和结束点

        beats = []
        # 因为量化的原因，乐曲真正的第一拍时间为480，因此这里从480开始
        current_time = 480
        for track in midi.tracks:
            for msg in track:
                if msg.type == "set_tempo":
                    current_time += msg.time
                    beats.append(current_time)

        return beats

    def beats_to_ticks(self, beats: float) -> int:
        """将beat转换为MIDI ticks"""
        return int(beats * self.ticks_per_beat)


def load_json_data(input_file: str) -> Dict[str, Any]:
    """加载JSON数据文件"""
    with open(input_file, "r", encoding="utf-8") as f:
        return json.load(f)


def convert_midi_to_fixed_tempo(
    input_midi_path: str, output_midi_path: str = None, target_bpm: int = 120
) -> str:
    """
    将量化后的MIDI文件转换为固定BPM的新MIDI文件，保持听感对齐
    只处理音符，创建单个轨道

    Args:
        input_midi_path: 输入MIDI文件路径
        output_midi_path: 输出MIDI文件路径（可选，默认在原文件名后加_120bpm）
        target_bpm: 目标BPM（默认120）

    Returns:
        输出文件路径
    """

    # 如果没有指定输出路径，自动生成
    if output_midi_path is None:
        base_name = os.path.splitext(input_midi_path)[0]
        output_midi_path = f"{base_name}_{target_bpm}bpm.mid"

    # 使用mido读取原始MIDI文件
    original_midi = mido.MidiFile(input_midi_path)

    # 提取所有音符事件及其绝对时间（秒）
    note_events = []
    current_tempo = 500000  # 默认tempo (120 BPM)
    ticks_per_beat = original_midi.ticks_per_beat
    accumulated_seconds = 0.0
    for msg in original_midi.merged_track:
        # 更新当前时间
        # 计算当前时间的秒数
        delta_seconds = mido.tick2second(msg.time, ticks_per_beat, current_tempo)

        accumulated_seconds += delta_seconds
        # 处理tempo变化
        if msg.type == "set_tempo":
            current_tempo = msg.tempo

        # 只收集音符事件
        if msg.type in ["note_on", "note_off"]:
            note_events.append((accumulated_seconds, msg))

    # 从note_events转换为notes（具有start time和end time）
    notes = []
    active_notes = {}  # {pitch: (start_time, velocity)}

    for time_seconds, msg in note_events:
        if msg.type == "note_on" and msg.velocity > 0:
            # 音符开始
            active_notes[msg.note] = (time_seconds, msg.velocity)

        elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
            # 音符结束
            if msg.note in active_notes:
                start_time, velocity = active_notes[msg.note]
                end_time = time_seconds

                # 创建note对象
                notes.append(
                    {
                        "pitch": msg.note,
                        "velocity": velocity,
                        "start": start_time,
                        "end": end_time,
                    }
                )

                # 从活跃音符中移除
                del active_notes[msg.note]

    # 创建新的MIDI文件
    new_midi = pretty_midi.PrettyMIDI(initial_tempo=target_bpm)
    instrument = pretty_midi.Instrument(program=0, is_drum=True)

    # 从notes创建pretty_midi.Note对象
    for note_data in notes:
        note = pretty_midi.Note(
            velocity=note_data["velocity"],
            pitch=note_data["pitch"],
            start=note_data["start"],
            end=note_data["end"],
        )
        instrument.notes.append(note)

    new_midi.instruments.append(instrument)
    new_midi.write(output_midi_path)

    return output_midi_path


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="优化的Beat到MIDI转换器，支持合并两个beat文件"
    )
    parser.add_argument(
        "-b1",
        "--beat-data1",
        required=True,
        help="allin1 beat信息JSON文件（不从0开始）",
    )
    parser.add_argument(
        "-b2", "--beat-data2", help="gorta beat信息JSON文件（从0开始，可选）"
    )
    parser.add_argument("-s", "--segment-data", help="segment信息JSON文件（可选）")
    parser.add_argument("-o", "--output", required=True, help="输出MIDI文件路径")
    parser.add_argument(
        "--ticks", type=int, default=480, help="MIDI时间分辨率 (默认: 480)"
    )
    parser.add_argument(
        "-p",
        "--loop_path",
        default="loops",
        help="鼓循环文件夹路径",
    )
    args = parser.parse_args()

    try:
        # 加载数据
        beat_data1 = load_json_data(args.beat_data1)

        beat_data2 = None
        if args.beat_data2:
            beat_data2 = load_json_data(args.beat_data2)

        segment_data = None
        if args.segment_data and os.path.exists(args.segment_data):
            segment_data = load_json_data(args.segment_data)

        # 生成MIDI
        converter = BeatMidiConverter(args.ticks)

        converter.generate_midi(
            beat_data1,
            beat_data2,
            segment_data,
            args.output,
            args.tolerance,
        )

    except Exception as e:
        print(f"错误: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
