use std::{convert::TryInto, net::SocketAddr, str::FromStr};

use clap::Parser;
use serde_json::json;
use stratum_apps::{
    key_utils::Secp256k1PublicKey,
    network_helpers::{connect_with_noise, resolve_host_port},
    stratum_core::{
        binary_sv2::U256,
        codec_sv2::StandardEitherFrame,
        common_messages_sv2::{Protocol, SetupConnection},
        framing_sv2::framing::Sv2Frame,
        mining_sv2::OpenStandardMiningChannel,
        parsers_sv2::{parse_message_frame_with_tlvs, AnyMessage, CommonMessages, IsSv2Message, Mining},
    },
};
use tokio::net::TcpStream;

#[derive(Parser, Debug)]
#[command(about = "Observe native SV2 SetNewPrevHash arrival timing")]
struct Args {
    #[arg(long)]
    host: String,
    #[arg(long)]
    port: u16,
    #[arg(long)]
    user: String,
    #[arg(long)]
    authority_pubkey: Option<String>,
}

fn frame(message: AnyMessage<'static>) -> Result<StandardEitherFrame<AnyMessage<'static>>, String> {
    let message_type = message.message_type();
    Ok(StandardEitherFrame::Sv2(
        Sv2Frame::from_message(message, message_type, 0, false)
            .ok_or_else(|| "unable to encode SV2 message".to_string())?,
    ))
}

fn parse_frame(frame: &mut StandardEitherFrame<AnyMessage<'static>>) -> Result<AnyMessage<'static>, String> {
    let StandardEitherFrame::Sv2(sv2) = frame else {
        return Err("unexpected handshake frame".to_string());
    };
    let header = sv2.get_header().ok_or("missing SV2 header")?;
    let (message, _) = parse_message_frame_with_tlvs(header, sv2.payload(), &[])
        .map_err(|error| format!("unable to parse SV2 frame: {error:?}"))?;
    Ok(message.into_static())
}

fn canonical_hash(prev_hash: &U256<'_>) -> String {
    let mut bytes = prev_hash.to_array();
    bytes.reverse();
    hex::encode(bytes)
}

#[tokio::main]
async fn main() -> Result<(), String> {
    let args = Args::parse();
    let address: SocketAddr = resolve_host_port(&format!("{}:{}", args.host, args.port))
        .await
        .map_err(|error| error.to_string())?;
    let stream = TcpStream::connect(address).await.map_err(|error| error.to_string())?;
    let authority = args
        .authority_pubkey
        .as_deref()
        .map(Secp256k1PublicKey::from_str)
        .transpose()
        .map_err(|error| error.to_string())?;
    let noise = connect_with_noise::<AnyMessage<'static>>(stream, authority)
        .await
        .map_err(|error| error.to_string())?;
    let (mut reader, mut writer) = noise.into_split();

    let setup = AnyMessage::Common(CommonMessages::SetupConnection(SetupConnection {
        protocol: Protocol::MiningProtocol,
        min_version: 2,
        max_version: 2,
        flags: 1, // Require Standard Channel jobs so timing reflects miner-visible work.
        endpoint_host: args.host.clone().try_into().map_err(|error| format!("{error:?}"))?,
        endpoint_port: args.port,
        vendor: "gridlabs-science".try_into().map_err(|error| format!("{error:?}"))?,
        hardware_version: "stratum-race".try_into().map_err(|error| format!("{error:?}"))?,
        firmware: "sv2-observer/0.1".try_into().map_err(|error| format!("{error:?}"))?,
        device_id: "timing-probe".try_into().map_err(|error| format!("{error:?}"))?,
    }));
    writer.write_frame(frame(setup)?).await.map_err(|error| error.to_string())?;

    loop {
        let mut incoming = reader.read_frame().await.map_err(|error| error.to_string())?;
        match parse_frame(&mut incoming)? {
            AnyMessage::Common(CommonMessages::SetupConnectionSuccess(_)) => break,
            AnyMessage::Common(CommonMessages::SetupConnectionError(error)) => {
                return Err(format!("SetupConnection rejected: {:?}", error.error_code));
            }
            _ => {}
        }
    }

    let open = AnyMessage::Mining(Mining::OpenStandardMiningChannel(
        OpenStandardMiningChannel {
            request_id: 1u32.into(),
            user_identity: args.user.try_into().map_err(|error| format!("{error:?}"))?,
            nominal_hash_rate: 1.0,
            max_target: vec![0xff; 32].try_into().map_err(|error| format!("{error:?}"))?,
        },
    ));
    writer.write_frame(frame(open)?).await.map_err(|error| error.to_string())?;
    println!("{}", json!({"event": "connected", "protocol": "sv2"}));

    loop {
        let mut incoming = reader.read_frame().await.map_err(|error| error.to_string())?;
        if let AnyMessage::Mining(Mining::SetNewPrevHash(message)) = parse_frame(&mut incoming)? {
            println!(
                "{}",
                json!({
                    "event": "set_new_prev_hash",
                    "prevhash": canonical_hash(&message.prev_hash),
                    "channel_id": message.channel_id,
                    "job_id": message.job_id,
                    "header_timestamp": message.min_ntime,
                    "template_class": "opaque"
                })
            );
        }
    }
}
