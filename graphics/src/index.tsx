// Registry: one Composition per template. Size, length and fps come from the props the engine sends:
// _w/_h (design units: 1920x1080 or 1080x1920), _frames, _fps (30 x motion-blur samples).
import React from "react";
import { Composition, registerRoot } from "remotion";
import * as Cards from "./cards";
import * as Scores from "./scores";
import * as Text from "./text";
import * as Marks from "./marks";
import * as Charts from "./charts";
import * as Thumbs from "./thumbs";
import * as Scenes from "./scenes";
import * as Media3D from "./media3d";
import * as Cinematic from "./cinematic";
import * as Motion from "./motion";
import * as S3D from "./scenes3d";
import * as Looks from "./looks";

export const TEMPLATES: Record<string, React.FC<any>> = {
  TitleCard: Cards.TitleCard, TestCard: Cards.TestCard, LogoHit: Cards.LogoHit, VersusCard: Cards.VersusCard, EndCard: Cards.EndCard, ShortEnd: Cards.ShortEnd, Cover: Cards.Cover, Text3D: Cards.Text3D, Contents: Cards.Contents,
  ScoreCard: Scores.ScoreCard, Scoreboard: Scores.Scoreboard, WordRace: Scores.WordRace, ClaimBoard: Scores.ClaimBoard,
  BigNumber: Scores.BigNumber, VerdictTable: Scores.VerdictTable,
  Captions: Text.Captions, Kinetic: Text.Kinetic, LowerThird: Text.LowerThird, Pill: Text.Pill, Chips: Text.Chips,
  ListReveal: Text.ListReveal, ChatThread: Text.ChatThread, StatPanel: Text.StatPanel,
  BarChart: Charts.BarChart, LineChart: Charts.LineChart, Donut: Charts.Donut, QuoteCard: Charts.QuoteCard, CodeBlock: Charts.CodeBlock,
  NewsCard: Charts.NewsCard, Frame: Charts.Frame, TopList: Charts.TopList, SubscribeHit: Charts.SubscribeHit,
  Thumbnail: Thumbs.Thumbnail, ThumbnailStyle: Thumbs.ThumbnailStyle,
  StageBackdrop: Scenes.StageBackdrop, ModelLadder: Scenes.ModelLadder, SafetySwitch: Scenes.SafetySwitch, CloudTrap: Scenes.CloudTrap, LightLeak: Scenes.LightLeak, Matte: Scenes.Matte,
  LottieClip: Media3D.LottieClip, Parallax: Media3D.Parallax, Device3D: Media3D.Device3D, BookReveal: Cinematic.BookReveal,
  DataCity: S3D.DataCity, NodeNetwork: S3D.NodeNetwork, CardTunnel: S3D.CardTunnel, ParticleWord: S3D.ParticleWord, GlobeArcs: S3D.GlobeArcs,
  TextFX: Motion.TextFX, FlowDiagram: Motion.FlowDiagram, TypeOn: Motion.TypeOn,
  Highlight: Marks.Highlight, Progress: Marks.Progress, Cursor: Marks.Cursor, Callout: Marks.Callout, Timer: Marks.Timer,
  Look: Looks.LookEl, LookBoard: Looks.LookBoard, LookMini: Looks.LookMini,
};

const Root: React.FC = () => (
  <>
    {Object.entries(TEMPLATES).map(([id, C]) => (
      <Composition key={id} id={id} component={C} width={1920} height={1080} fps={30} durationInFrames={90} defaultProps={{}}
        calculateMetadata={({ props }: any) => ({ width: props._w || 1920, height: props._h || 1080, fps: props._fps || 30, durationInFrames: Math.max(1, props._frames || 90) })} />
    ))}
  </>
);
registerRoot(Root);
